from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

DATABASE_URI = os.getenv('POSTGRES_URI_CUSTOM')


# Global checkpointer variable
checkpointer = None
pool = None

async def init_checkpointer():
    global checkpointer, pool
    if checkpointer is None:
        try:
            # ✅ create a persistent connection pool
            pool = AsyncConnectionPool(conninfo=DATABASE_URI, max_size=10, kwargs={"autocommit": True})
            
            # ✅ create a saver using the pool
            saver = AsyncPostgresSaver(pool)
            await saver.setup()

            checkpointer = saver
            print("[INFO] AsyncPostgresSaver initialized and schema setup completed.")
        except Exception as e:
            print(f"[ERROR] Failed to initialize AsyncPostgresSaver: {e}")
            checkpointer = None
    return checkpointer
