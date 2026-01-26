import os
from langgraph.store.postgres.aio import AsyncPostgresStore
from src.utils.embedding import get_embedding

DB_URI = os.getenv("POSTGRES_URI_CUSTOM")
embeddings = get_embedding()

def embed_texts(texts: list[str]) -> list[list[float]]:
    return embeddings.embed_documents(texts)

def create_long_term_store() -> AsyncPostgresStore:
    if not DB_URI:
        raise RuntimeError("POSTGRES_URI_CUSTOM is not set")

    # from_conn_string already returns async context manager
    return AsyncPostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": 1536,
            "embed": embed_texts,
        },
    )


