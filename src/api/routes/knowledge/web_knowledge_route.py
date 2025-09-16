from fastapi import (
    APIRouter, Depends,
    HTTPException,
    BackgroundTasks
)
from pydantic import HttpUrl
from src.utils.logger import logger
# from src.api.models.knowledge_model import KnowledgeModel, Website
from src.api.tasks.knowledge_task import scrape_web_content

from sqlalchemy.orm import Session
from src.api.database.database import get_db

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


# # CREATE
# @router.post("/create")
# def create_knowledge(
#     url:HttpUrl,
#     db: Session = Depends(get_db),
#     background_tasks: BackgroundTasks = None
#         ):
#     try:
#         logger.info(f"Creating Knowledge Base from URL... {url}")
#
#         # Check for duplicate URL
#         existing_website = db.query(Website).filter(Website.url == str(url)).first()
#         if existing_website:
#             logger.warning(f"Website with URL '{url}' already exists.")
#             raise HTTPException(
#                 status_code=400,
#                 detail="Website with this URL already exists."
#             )
#
#         # Create knowledge entry
#         knowledge = KnowledgeModel(
#             title=f"Knowledge from {url}",
#             description=f"Auto-generated knowledge base from {url}"
#         )
#         db.add(knowledge)
#         db.commit()
#         db.refresh(knowledge)
#
#         # Add to Website table
#         website = Website(
#             url=str(url),
#             knowledge_id=knowledge.id
#         )
#         db.add(website)
#         db.commit()
#         db.refresh(website)
#
#         # Trigger background task to scrape content
#         if background_tasks:
#             background_tasks.add_task(scrape_web_content, str(url), website.id)
#
#         return {
#             "message": "Knowledge base created successfully.",
#             "knowledge_id": knowledge.id,
#             "website_id": website.id
#         }
#     except Exception as e:
#         logger.error(f"Error creating knowledge: {e}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")
#
#
# # Get all
# @router.get("/all")
# def get_all_knowledge(db: Session = Depends(get_db)):
#     try:
#         logger.info("Fetching all knowledge entries...")
#         knowledge_entries = db.query(Website).all()
#         return {"knowledge_entries": knowledge_entries}
#     except Exception as e:
#         logger.error(f"Error fetching knowledge entries: {e}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")
#
# # Get by id
# @router.get("/{knowledge_id}/{web_id}")
# def get_knowledge_by_id(
#     knowledge_id: str,
#     web_id: str,
#     db: Session = Depends(get_db)
#     ):
#     try:
#         logger.info(f"Fetching knowledge entry with ID: {knowledge_id}")
#         knowledge_entry = (
#             db.query(KnowledgeModel)
#             .filter(
#                 KnowledgeModel.id == knowledge_id,
#                 KnowledgeModel.web_id == web_id
#             )
#             .first()
#         )
#
#         if not knowledge_entry:
#             raise HTTPException(status_code=404, detail="Knowledge entry not found")
#
#         # Convert SQLAlchemy model to dict
#         return {"knowledge_entry": knowledge_entry.__dict__}
#     except Exception as e:
#         logger.error(f"Error fetching knowledge entry: {e}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")
#
# # Delete
# @router.delete("/{knowledge_id}")
# def delete_knowledge(knowledge_id: int, db: Session = Depends(get_db)):
#     try:
#         logger.info(f"Deleting knowledge entry with ID: {knowledge_id}")
#         knowledge_entry = db.query(KnowledgeModel).filter(KnowledgeModel.id == knowledge_id).first()
#         if not knowledge_entry:
#             raise HTTPException(status_code=404, detail="Knowledge entry not found")
#
#         # Also delete associated websites
#         db.query(Website).filter(Website.knowledge_id == knowledge_id).delete()
#
#         db.delete(knowledge_entry)
#         db.commit()
#         return {"message": "Knowledge entry deleted successfully"}
#     except Exception as e:
#         logger.error(f"Error deleting knowledge entry: {e}")
#         raise HTTPException(status_code=500, detail="Internal Server Error")