from fastapi import (
    APIRouter, Depends,
    HTTPException,
    BackgroundTasks
)
from src.utils.logger import logger
# from src.api.models.knowledge_model import KnowledgeModel, Website
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from typing import List


router = APIRouter(
    prefix="/workspace/file",
    tags=["file_knowledge"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status():
    logger.info("file Knowledge Route health check called.")
    return {"status": "file Knowledge Route is working!"}
