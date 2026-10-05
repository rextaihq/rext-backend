#!/usr/bin/env python3
"""Fetch and keep the favicon of every workspace that has a site but no favicon yet.

New workspaces get theirs from the creation pipeline; this is for the ones made
before it did. It reads each workspace's homepage, takes its favicon through the
same checks (SSRF-checked addresses, capped bodies, raster images only) and
stores it in the media store. A workspace whose site has no usable icon is left
as it is; a second run only retries those.

Usage:
    python scripts/backfill_workspace_favicons.py [--dry-run]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from sqlalchemy import select  # noqa: E402

from src.api.database.async_database import get_async_db_context  # noqa: E402
from src.api.models.workspace_models.workspace_model import WorkspaceModel  # noqa: E402
from src.services.workspace_favicon import (  # noqa: E402
    fetch_page_html,
    find_favicon,
    store_favicon,
)


async def backfill(dry_run: bool) -> dict:
    counts = {"checked": 0, "stored": 0, "no_icon": 0}
    async with get_async_db_context() as db:
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.url.isnot(None),
                WorkspaceModel.favicon_url.is_(None),
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        for workspace in result.scalars().all():
            counts["checked"] += 1
            try:
                html = await fetch_page_html(workspace.url)
            except Exception as exc:  # noqa: BLE001 - one site's failure is not the run's
                print(f"{workspace.slug}: homepage not read ({type(exc).__name__})")
                html = None
            found = await find_favicon(html, workspace.url)
            if not found:
                counts["no_icon"] += 1
                print(f"{workspace.slug}: no usable favicon")
                continue
            print(f"{workspace.slug}: {found['mime']} from {found['source_url']}")
            if dry_run:
                continue
            object_name = await store_favicon(str(workspace.id), found["data"], found["mime"])
            if object_name:
                workspace.favicon_url = object_name
                counts["stored"] += 1
        if not dry_run:
            await db.commit()
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="find the icons, store nothing")
    print(asyncio.run(backfill(parser.parse_args().dry_run)))
