import asyncio
from typing import Optional

_main_loop: Optional[asyncio.AbstractEventLoop] = None


def register(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def get() -> Optional[asyncio.AbstractEventLoop]:
    return _main_loop
