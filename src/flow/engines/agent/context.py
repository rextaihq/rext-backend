from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RextContext:
    """
    Runtime context injected into the agent at invocation time.
    Provides dependency-injected resources (e.g. DB session) accessible
    by middleware and tools via runtime.context.
    """
    db: AsyncSession
