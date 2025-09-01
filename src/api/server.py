# Standard library imports
import os
from contextlib import asynccontextmanager
from typing import Union

# Third-party imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from distro import name
from dotenv import load_dotenv

# Local application imports
# from src.api.routes.user_routes import router as user_router
from src.api.routes.topic_generation_route import router as topic_router
# from src.api.database.database import Base, engine
# from src.api.models.models import User

load_dotenv()

# DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

# Create the database tables
# Base.metadata.create_all(bind=engine)

# @asynccontextmanager
# async def lifespan(app: FastAPI):

#     engine = create_async_engine(DB_URI)
#     # Create reusable session factory
#     async_session = sessionmaker(engine, class_=AsyncSession)
#     # Store in app state
#     app.state.db_session = async_session
#     yield
#     # Clean up connections
#     await engine.dispose()

app = FastAPI(
    name="Content Automation API",
    version="1.0.0",
    description="API for managing content automation workflows",
    # lifespan=lifespan
)

# Allow your frontend origi
app.add_middleware(
    CORSMiddleware,
    allow_origins="*",        # allow specific origins
    allow_credentials=True,
    allow_methods=["*"],          # allow all HTTP methods
    allow_headers=["*"],          # allow all headers
)

# Fixing he issue async issue only in workflow routes
# app.include_router(user_router, prefix="/api", tags=["user"])
app.include_router(topic_router, prefix="/api", tags=["topic_generation_routes"])

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)