from typing import Union

from distro import name
from src.api.routes.workflowRoutes import router as workflow_router
from fastapi import FastAPI
# from src.utils.checkpoiner import init_checkpointer
# from contextlib import asynccontextmanager  

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     await init_checkpointer()  # this sets the global variable
#     yield


app = FastAPI(
    name="Content Automation API",
    version="1.0.0",
    description="API for managing content automation workflows",
    # lifespan=lifespan,
)

app.include_router(workflow_router, prefix="/api", tags=["workflow"])


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)