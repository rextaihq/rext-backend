from fastapi import (
    APIRouter, Depends,
    HTTPException,
    BackgroundTasks
)
from src.utils.logger import logger
from src.api.schema.knowledge_schema import KnowledgeSchema
from src.api.models.knowledge_model import KnowledgeModel, Website
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from typing import List

router = APIRouter(
    prefix="/knowledge/web",
    tags=["web_knowledge"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status():
    logger.info("web Knowledge Route health check called.")
    return {"status": "Web Knowledge Route is working!"}
