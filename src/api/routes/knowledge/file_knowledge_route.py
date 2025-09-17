from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
    BackgroundTasks
)
from src.utils.logger import logger
# from src.api.models.knowledge_model import KnowledgeModel, Website
from src.utils.response_utils import success
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
def get_status(request: Request):
    logger.info("File Knowledge Route health check called.")
    return success(
        data={"status": "operational", "service": "file_knowledge_service"},
        request=request,
        message="File Knowledge Route is working!"
    )
