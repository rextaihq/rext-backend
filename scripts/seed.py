#!/usr/bin/env python3
"""Seed the data every database needs: the subscription plans, the promotions,
the roles and permissions, the super admin named by the environment and the API
usage rollup's row.

Run it after `alembic upgrade head` on every environment (`python scripts/db.py
migrate` does both, and sets up the LangGraph store). It only inserts what is
missing: a second run changes nothing, and an existing plan, role or account is
never overwritten.

Usage:
    python scripts/seed.py
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

from scripts.seeds.run_all import run_all_seeds  # noqa: E402

if __name__ == "__main__":
    asyncio.run(run_all_seeds())
