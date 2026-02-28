from langgraph.store.postgres.aio import AsyncPostgresStore
from src.utils.embedding import get_embedding
from langchain.embeddings import init_embeddings, Embeddings
from langgraph.store.base import IndexConfig
from typing import cast
import contextlib
import os


DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

embeddings = cast(Embeddings, init_embeddings("openai:text-embedding-3-small"))

@contextlib.asynccontextmanager
async def generate_store():
    """Yield a BaseStore, open for the duration of the server."""
    async with AsyncPostgresStore.from_conn_string(
        DB_URI,
        index=IndexConfig(
            dims=1536,
            embed=embeddings,
            fields=[],
        ),
    ) as store:
        await store.setup()
        yield store