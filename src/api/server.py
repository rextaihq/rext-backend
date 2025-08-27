from typing import Union

from distro import name
from src.api.routes.userRoutes import router as user_router
from fastapi import FastAPI
from src.api.database.database import Base, engine
from src.api.models.models import User

# Create the database tables
Base.metadata.create_all(bind=engine)


app = FastAPI(
    name="Content Automation API",
    version="1.0.0",
    description="API for managing content automation workflows",
    # lifespan=lifespan,
)
# Fixing he issue async issue only in workflow routes
app.include_router(user_router, prefix="/api", tags=["user"])

@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)