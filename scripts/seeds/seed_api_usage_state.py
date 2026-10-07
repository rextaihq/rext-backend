"""Seed the API usage rollup's bookkeeping row."""

import asyncio

from sqlalchemy import text

from scripts.seeds.base import get_seed_session


async def seed_api_usage_state():
    """The rollup keeps how far it has settled in row 1; it starts with nothing settled."""
    async with get_seed_session() as session:
        result = await session.execute(
            text(
                "INSERT INTO api_usage_rollup_state (id, settled_through) VALUES (1, NULL) "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        print(f"API usage rollup state: {'created' if result.rowcount else 'already existed'}")


if __name__ == "__main__":
    asyncio.run(seed_api_usage_state())
