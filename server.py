"""Convenience entrypoint for local API startup."""

import uvicorn
import sys
import asyncio


if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

if __name__ == "__main__":
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=2024,
        reload=False,
    )