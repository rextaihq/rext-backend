"""
CMS Publishing Status Report
-----------------------------
Queries all non-deleted content and their per-site publishing records,
then optionally syncs live status from WordPress/Shopify.

Usage:
    python scripts/check_cms_status.py              # DB snapshot only
    python scripts/check_cms_status.py --sync       # live-sync from CMS first
    python scripts/check_cms_status.py --workspace <uuid>  # filter workspace
"""

import asyncio
import os
import sys
import argparse
from datetime import timezone
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

# ── DB setup ────────────────────────────────────────────────────────────────

def _get_async_url():
    uri = os.getenv("POSTGRES_URI_CUSTOM", "")
    if not uri:
        sys.exit("POSTGRES_URI_CUSTOM not set in .env")
    if not uri.startswith("postgresql+asyncpg"):
        uri = uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    return uri


# ── Formatting helpers ───────────────────────────────────────────────────────

STATUS_COLORS = {
    "published": "\033[92m",   # green
    "draft":     "\033[93m",   # yellow
    "trashed":   "\033[91m",   # red
    "deleted":   "\033[91m",   # red
    "unknown":   "\033[90m",   # grey
}
RESET = "\033[0m"

def _colorize(status: str) -> str:
    color = STATUS_COLORS.get((status or "unknown").lower(), "")
    return f"{color}{(status or 'unknown').upper()}{RESET}"

def _truncate(s, n=50):
    if not s:
        return "—"
    return s if len(s) <= n else s[:n - 1] + "…"


# ── Core query ───────────────────────────────────────────────────────────────

QUERY = """
SELECT
    c.id                    AS content_id,
    c.title                 AS content_title,
    c.status                AS rext_status,
    c.created_at            AS created_at,
    cpr.id                  AS pub_id,
    cpr.status              AS cms_status,
    cpr.wp_post_id,
    cpr.shopify_article_id,
    cpr.external_url,
    cpr.last_synced_at,
    cpr.sync_error,
    wi.site_url,
    wi.integration_type,
    wi.is_active            AS site_active,
    w.slug                  AS workspace_slug
FROM content c
JOIN workspace w ON w.id = c.workspace_id
LEFT JOIN content_publishing_results cpr ON cpr.content_id = c.id
LEFT JOIN integrations wi ON wi.id = cpr.site_id
WHERE c.deleted_at IS NULL
{workspace_filter}
ORDER BY c.created_at DESC, wi.site_url
"""


async def fetch_rows(workspace_id=None):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(_get_async_url())
    try:
        wf = "AND c.workspace_id = :wsid" if workspace_id else ""
        async with engine.connect() as conn:
            params = {"wsid": workspace_id} if workspace_id else {}
            result = await conn.execute(
                text(QUERY.format(workspace_filter=wf)), params
            )
            return result.mappings().all()
    finally:
        await engine.dispose()


# ── Live sync ────────────────────────────────────────────────────────────────

async def live_sync(pub_ids: list[str]):
    """Call CMSStatusService for each publishing record that needs a sync."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(_get_async_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Import here so models register against the metadata
    from src.api.models.content_models.publishing_result import ContentPublishingResult  # noqa
    from src.api.models.integrations.workspace_integration import WorkspaceIntegration  # noqa
    from src.services.cms_status_service import CMSStatusService

    synced = 0
    errors = 0

    async with async_session() as db:
        svc = CMSStatusService(db)
        for raw_id in pub_ids:
            try:
                updated = await svc.sync_content_status(UUID(raw_id))
                if updated:
                    synced += 1
                    print(f"  synced {raw_id} → {updated.status}")
            except Exception as e:
                errors += 1
                print(f"  FAILED {raw_id}: {e}")
        await db.commit()

    await engine.dispose()
    return synced, errors


# ── Report ───────────────────────────────────────────────────────────────────

def print_report(rows):
    if not rows:
        print("No content found.")
        return

    # Group by content
    from collections import defaultdict
    by_content: dict[str, list] = defaultdict(list)
    content_meta: dict[str, dict] = {}

    for row in rows:
        cid = str(row["content_id"])
        by_content[cid].append(row)
        if cid not in content_meta:
            content_meta[cid] = {
                "title": row["content_title"],
                "rext_status": row["rext_status"],
                "created_at": row["created_at"],
                "workspace": row["workspace_slug"],
            }

    # Counters
    total_content = len(by_content)
    total_pub_records = sum(1 for r in rows if r["pub_id"])
    cms_status_counts: dict[str, int] = {}

    print("\n" + "=" * 80)
    print(f"  CMS PUBLISHING STATUS REPORT — {total_content} article(s)")
    print("=" * 80)

    for cid, pub_rows in by_content.items():
        meta = content_meta[cid]
        ts = meta["created_at"]
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if ts else "—"
        print(f"\n▸ [{meta['workspace']}]  {_truncate(meta['title'], 60)}")
        print(f"  rext_status={_colorize(meta['rext_status'])}   created={ts_str}")

        has_pub = any(r["pub_id"] for r in pub_rows)
        if not has_pub:
            print("  └─ No publishing records (never published or migration pending)")
            continue

        for r in pub_rows:
            if not r["pub_id"]:
                continue
            cms = (r["cms_status"] or "unknown").lower()
            cms_status_counts[cms] = cms_status_counts.get(cms, 0) + 1

            platform = r["integration_type"] or "?"
            site = _truncate(r["site_url"] or "?", 40)
            active_tag = "" if r["site_active"] else " [INACTIVE]"

            native_id = (
                f"wp_id={r['wp_post_id']}" if r["wp_post_id"]
                else f"shopify_id={r['shopify_article_id']}" if r["shopify_article_id"]
                else "no_native_id"
            )

            synced_at = r["last_synced_at"]
            synced_str = synced_at.strftime("%Y-%m-%d %H:%M") if synced_at else "never synced"

            url = _truncate(r["external_url"] or "", 60)

            print(f"  ├─ {platform.upper()}{active_tag}  {site}")
            print(f"  │   cms_status={_colorize(cms)}   {native_id}   synced={synced_str}")
            if url and url != "—":
                print(f"  │   url={url}")
            if r["sync_error"]:
                print(f"  │   ⚠  sync_error: {_truncate(r['sync_error'], 80)}")

    print("\n" + "-" * 80)
    print(f"  Total articles: {total_content}   Publishing records: {total_pub_records}")
    if cms_status_counts:
        status_summary = "   ".join(
            f"{_colorize(s)}={n}" for s, n in sorted(cms_status_counts.items())
        )
        print(f"  CMS statuses:  {status_summary}")
    print("=" * 80 + "\n")


# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="CMS publishing status report")
    parser.add_argument("--sync", action="store_true", help="Live-sync from CMS before reporting")
    parser.add_argument("--workspace", default=None, help="Filter to a specific workspace UUID")
    args = parser.parse_args()

    workspace_id = args.workspace

    if args.sync:
        print("Fetching publishing records to sync…")
        rows_pre = await fetch_rows(workspace_id)
        pub_ids = [str(r["pub_id"]) for r in rows_pre if r["pub_id"]]
        if not pub_ids:
            print("No publishing records to sync.")
        else:
            print(f"Syncing {len(pub_ids)} record(s) from CMS…")
            synced, errors = await live_sync(pub_ids)
            print(f"Done: {synced} synced, {errors} failed.\n")

    rows = await fetch_rows(workspace_id)
    print_report(rows)


if __name__ == "__main__":
    asyncio.run(main())
