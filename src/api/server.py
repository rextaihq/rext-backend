from typing import Union
from src.api.routes.workflowRoutes import router as workflow_router
from fastapi import FastAPI

app = FastAPI()
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