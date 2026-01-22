# src/memory/postgres_store.py
import os
from langgraph.store.postgres import PostgresStore
from src.utils.embedding import get_embedding

DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

def create_long_term_store() -> PostgresStore:
    embeddings = get_embedding()

    def embed_texts(texts: list[str]) -> list[list[float]]:
        return embeddings.embed_documents(texts)

    return PostgresStore.from_conn_string(
        DB_URI,
        index={
            "dims": 1536,  # must match embedding model
            "embed": embed_texts,
        },
    )
