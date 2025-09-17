from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
)
from src.utils.logger import logger
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.api.models.knowledge_model import Website
from src.model.model import load_model
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper
from src.utils.response_utils import success, error, created, not_found, conflict, no_content
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException
)
from datetime import datetime, timezone


router = APIRouter(
    prefix="/web_knowledge",
    tags=["WebKnowledge"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
def get_status():
    return success(data={"status": "Web Knowledge Route is operational"})

# get knowwledes
def get_web_knowledges(request: Request, db: Session = Depends(get_db)):
    try:
        logger.info("Fetching all web knowledges")
        web_knowledges = db.query(Website).all()
        return success(data=[knowledge.to_dict() for knowledge in web_knowledges])
    except Exception as e:
        logger.error(f"Error fetching knowledges: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    

# Get knowledge by ID
def get_web_knowledge(web_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        logger.info(f"Fetching knowledge with ID: {web_id}")
        knowledge = db.query(Website).filter(Website.id == web_id).first()
        if not knowledge:
            raise ResourceNotFoundException(f"Knowledge with ID {web_id} not found")
        return success(data=knowledge.to_dict())
    except ResourceNotFoundException as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching knowledge: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
# Add new knowledge
# def 
