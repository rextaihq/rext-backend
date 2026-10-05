"""The tables the LangGraph server and the LangGraph store own.

They live beside the application's tables (the store always; the runtime unless
DATABASE_URI points at a database of its own) but have no models: the server
creates and migrates them when it starts. Alembic must never touch them
(alembic/env.py) and a reset must never drop them (scripts/db.py).
"""

LANGGRAPH_TABLES = frozenset(
    {
        # the runtime (langgraph-api)
        "assistant",
        "assistant_versions",
        "checkpoint_blobs",
        "checkpoint_delete_queue",
        "checkpoint_migrations",
        "checkpoint_writes",
        "checkpoints",
        "cron",
        "queue",
        "resumable_streams",
        "run",
        "schema_migrations",
        "thread",
        "thread_ttl",
        # the store (langgraph.store.postgres, src/flow/store/rext_store.py)
        "store",
        "store_migrations",
        "store_vectors",
        "vector_migrations",
    }
)
