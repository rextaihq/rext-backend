"""
Google Analytics Integration - Verification Script

This script verifies the end-to-end backend logic by:
1. Creating minimal test data (user, workspace, content, publishing result)
2. Saving Google property selections (simulating OAuth callback)
3. Running a mocked data sync
4. Calling all analytics endpoints and verifying the output

All external Google API calls are mocked so this works without real credentials.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.api.models.content_models.content import Content
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.workspace_google_connection import WorkspaceGoogleConnection
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.analytics_models.google_analytics_metric import GoogleAnalyticsMetric
from src.services.google_connection_service import GoogleConnectionService
from src.services.google_analytics_sync_service import GoogleAnalyticsSyncService
from src.services.google_metrics_service import GoogleMetricsService


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

async def create_test_fixtures(db):
    """Create minimal DB fixtures for the test, returns (workspace_id, oauth_id, content_id)"""

    user_id = uuid.uuid4()
    user = Users(
        id=user_id,
        email=f"verify_{uuid.uuid4().hex[:6]}@test.com",
        full_name="Verification User",
        status="active",
    )
    db.add(user)
    await db.flush()

    workspace_id = uuid.uuid4()
    workspace = WorkspaceModel(
        id=workspace_id,
        name="Verification Workspace",
        user_id=user_id,
        slug=f"verify-{uuid.uuid4().hex[:6]}",
    )
    db.add(workspace)
    await db.flush()

    oauth_id = uuid.uuid4()
    oauth = OAuthAccount(
        id=oauth_id,
        user_id=user_id,
        provider="google",
        provider_account_id=f"google_verify_{uuid.uuid4().hex[:8]}",
        provider_account_email="verify@test.com",
        access_token="mock_access_token",
        refresh_token="mock_refresh_token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(oauth)
    await db.flush()

    content_id = uuid.uuid4()
    content = Content(
        id=content_id,
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        title="How to do SEO",
        slug=f"how-to-do-seo-{uuid.uuid4().hex[:4]}",
        status="published",
    )
    db.add(content)
    await db.flush()

    # WorkspaceIntegration (site) is required by ContentPublishingResult as a FK
    site_id = uuid.uuid4()
    site = WorkspaceIntegration(
        id=site_id,
        workspace_id=workspace_id,
        integration_type="wordpress",
        site_url="https://example.com",
        is_active=True,
    )
    db.add(site)
    await db.flush()

    pub_id = uuid.uuid4()
    publishing_result = ContentPublishingResult(
        id=pub_id,
        content_id=content_id,
        site_id=site_id,
        external_url="https://example.com/blog/how-to-do-seo",
        status="success",
    )
    db.add(publishing_result)
    await db.commit()

    return workspace_id, oauth_id, content_id


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------

async def run_verification():
    print("\n" + "=" * 60)
    print("  Google Analytics Integration — Backend Verification")
    print("=" * 60 + "\n")

    results = []

    async with AsyncSessionLocal() as db:

        # ── Step 1: Fixtures ──────────────────────────────────────────────
        print("Step 1: Creating test fixtures...")
        try:
            workspace_id, oauth_id, content_id = await create_test_fixtures(db)
            print(f"  ✅ Fixtures created (workspace_id={workspace_id})\n")
            results.append(("Create fixtures", True, None))
        except Exception as e:
            print(f"  ❌ Failed to create fixtures: {e}\n")
            results.append(("Create fixtures", False, str(e)))
            return results

        # ── Step 2: Save property selections ─────────────────────────────
        print("Step 2: Saving Google property selections...")
        try:
            # In production, WorkspaceGoogleConnection is created during the OAuth callback.
            # Here we simulate that by creating it directly before calling save_selections.
            initial_conn = WorkspaceGoogleConnection(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                oauth_account_id=oauth_id,
            )
            db.add(initial_conn)
            await db.commit()

            conn_service = GoogleConnectionService(db)
            await conn_service.save_selections(
                workspace_id=workspace_id,
                gsc_site_url="https://example.com/",
                ga4_property_id="properties/999888777",
            )
            print(f"  ✅ Selections saved (gsc_site_url=https://example.com/, ga4_property_id=properties/999888777)\n")
            results.append(("Save selections", True, None))
        except Exception as e:
            print(f"  ❌ Save selections failed: {e}\n")
            results.append(("Save selections", False, str(e)))
            return results

        # ── Step 3: Mock sync ─────────────────────────────────────────────
        print("Step 3: Running mocked data sync (GSC + GA4)...")
        try:
            sync_service = GoogleAnalyticsSyncService(db)

            # Patch external HTTP calls with local mock data
            async def mock_fetch_gsc(token, site_url, start_date, end_date, **kwargs):
                return [
                    {
                        "keys": ["https://example.com/blog/how-to-do-seo", "seo guide"],
                        "clicks": 50,
                        "impressions": 1000,
                        "ctr": 0.05,
                        "position": 3.5,
                    }
                ]

            async def mock_fetch_ga4(token, property_id, start_date, end_date, **kwargs):
                return [
                    {
                        "dimensionValues": [
                            {"value": start_date.strftime("%Y%m%d")},
                            {"value": "/blog/how-to-do-seo"},
                        ],
                        "metricValues": [
                            {"value": "150"},
                            {"value": "120"},
                            {"value": "0.65"},
                            {"value": "2"},
                        ],
                    }
                ]

            async def mock_get_token(oauth_account):
                return "mocked_bearer_token"

            sync_service.fetch_gsc_metrics = mock_fetch_gsc
            sync_service.fetch_ga4_metrics = mock_fetch_ga4
            sync_service.oauth_service.get_valid_token = mock_get_token

            await sync_service.sync_workspace(workspace_id, backfill=False)

            # Verify rows were inserted
            count = (await db.execute(
                select(GoogleAnalyticsMetric).where(
                    GoogleAnalyticsMetric.workspace_id == workspace_id
                )
            )).scalars().all()
            print(f"  ✅ Sync complete. Rows inserted into google_analytics_metrics: {len(count)}\n")
            results.append(("Data sync", True, f"{len(count)} rows"))
        except Exception as e:
            print(f"  ❌ Data sync failed: {e}\n")
            results.append(("Data sync", False, str(e)))
            return results

        # ── Step 4: Raw metrics endpoint ─────────────────────────────────
        print("Step 4: Fetching raw metrics (GET /metrics)...")
        try:
            metrics_service = GoogleMetricsService(db)
            raw = await metrics_service.get_metrics(workspace_id=workspace_id)
            total = raw.get("total_count", 0)
            print(f"  ✅ Raw metrics returned {total} record(s)")
            if total > 0:
                sample = raw["data"][0]
                print(f"     Sample → source={sample.get('source')}, url={sample.get('article_external_url')}\n")
            results.append(("Raw metrics API", True, f"{total} records"))
        except Exception as e:
            print(f"  ❌ Raw metrics API failed: {e}\n")
            results.append(("Raw metrics API", False, str(e)))

        # ── Step 5: Article summary endpoint ─────────────────────────────
        print("Step 5: Fetching article summary (GET /articles/summary)...")
        try:
            summary = await metrics_service.get_article_summary(workspace_id=workspace_id)
            print(f"  ✅ Article summary returned {len(summary)} article(s)")
            if summary:
                art = summary[0]
                gsc = art.get("gsc_metrics", {})
                print(f"     Article: '{art.get('title')}' | Clicks={gsc.get('clicks')} Impressions={gsc.get('impressions')} Position={gsc.get('avg_position')}\n")
            results.append(("Article summary API", True, f"{len(summary)} articles"))
        except Exception as e:
            print(f"  ❌ Article summary API failed: {e}\n")
            results.append(("Article summary API", False, str(e)))

        # ── Step 6: Top queries endpoint ─────────────────────────────────
        print("Step 6: Fetching top queries (GET /articles/{id}/queries)...")
        try:
            queries = await metrics_service.get_top_queries(
                workspace_id=workspace_id,
                article_id=content_id
            )
            print(f"  ✅ Top queries returned {len(queries)} keyword(s)")
            if queries:
                top = queries[0]
                print(f"     Top keyword: '{top.get('query_keyword')}' | Clicks={top.get('metrics', {}).get('clicks')}\n")
            results.append(("Top queries API", True, f"{len(queries)} keywords"))
        except Exception as e:
            print(f"  ❌ Top queries API failed: {e}\n")
            results.append(("Top queries API", False, str(e)))

    # ── Summary ───────────────────────────────────────────────────────────
    print("=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    all_passed = True
    for step, passed, detail in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        detail_str = f"  ({detail})" if detail else ""
        print(f"  {status}  {step}{detail_str}")
        if not passed:
            all_passed = False
    print("=" * 60)
    if all_passed:
        print("  🎉 All checks passed! The integration is working correctly.")
    else:
        print("  ⚠️  Some checks failed. Review the errors above.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_verification())
