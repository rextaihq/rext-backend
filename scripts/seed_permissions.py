"""Compatibility entry point for the canonical idempotent RBAC seed."""

import asyncio

from scripts.seeds.seed_permissions import seed_permissions


if __name__ == "__main__":
    asyncio.run(seed_permissions())
