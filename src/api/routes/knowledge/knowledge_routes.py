from fastapi import (
    APIRouter, Depends, Request,
    HTTPException,
    BackgroundTasks
)
from src.utils.logger import logger
from src.api.schema.knowledge_schema import KnowledgeSchema
from src.api.models.knowledge_model import Website
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.response_utils import success
from typing import List
from src.api.tasks.knowledge_task import scrape_web_content

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status(request: Request):
    logger.info("Knowledge Route health check called.")
    return success(
        data={"status": "operational", "service": "knowledge_service"},
        request=request,
        message="Knowledge Route is working!"
    )


# # CREATE
# @router.post("/create")
# def create_knowledge(
#         data: KnowledgeSchema,
#         db: Session = Depends(get_db),
#         background_tasks: BackgroundTasks = None
# ):
#     try:
#         logger.info(f"Creating Knowledge Base... {data.title}")
#
#         # Check for duplicate title
#         existing_knowledge = db.query(KnowledgeModel).filter(KnowledgeModel.title == data.title).first()
#         if existing_knowledge:
#             logger.warning(f"Knowledge with title '{data.title}' already exists.")
#             raise HTTPException(
#                 status_code=400,
#                 detail="Knowledge with this title already exists."
#             )
#
#         # Create knowledge
#         knowledge = KnowledgeModel(
#             title=data.title,
#             description=getattr(data, "description", None)
#         )
#         db.add(knowledge)
#         db.commit()
#         db.refresh(knowledge)
#
#         # If URL provided → add to Website table
#         if data.url:
#             logger.info(f"Checking if website already exists: {data.url}")
#             existing_website = db.query(Website).filter(Website.url == str(data.url)).first()
#             if existing_website:
#                 logger.warning(f"Website with URL '{data.url}' already exists.")
#                 raise HTTPException(
#                     status_code=400,
#                     detail="Website with this URL already exists."
#                 )
#
#             website = Website(
#                 knowledge_id=knowledge.id,
#                 url=str(data.url),
#                 status="process"
#             )
#             db.add(website)
#             db.commit()
#             db.refresh(website)
#
#             logger.info("Added scraping task to background queue")
#             background_tasks.add_task(scrape_web_content, str(data.url), website.id)
#
#         return {
#             "status": 200,
#             "message": "Knowledge Created Successfully",
#             "knowledge_id": str(knowledge.id),
#         }
#     except Exception as e:
#         logger.error(f"Error occurred while creating knowledge: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail="Internal Server Error"
#         )
#
# # GET (all or by ID)
# @router.get("/list", response_model=List[KnowledgeSchema])
# def list_knowledge(db: Session = Depends(get_db)):
#     """
#     Fetch all knowledge entries.
#     """
#     logger.info("Fetching all knowledge bases...")
#     knowledge_list = db.query(KnowledgeModel).all()
#     return knowledge_list
#
#
# @router.get("/{knowledge_id}", response_model=KnowledgeSchema)
# def get_knowledge(knowledge_id: str, db: Session = Depends(get_db)):
#     """
#     Fetch knowledge by ID.
#     """
#     logger.info(f"Fetching knowledge with ID {knowledge_id}")
#     knowledge = db.query(KnowledgeModel).filter(KnowledgeModel.id == knowledge_id).first()
#     if not knowledge:
#         raise HTTPException(status_code=404, detail="Knowledge not found")
#     return knowledge
#
#
# # DELETE
# @router.delete("/{knowledge_id}")
# def delete_knowledge(knowledge_id: str, db: Session = Depends(get_db)):
#     """
#     Delete knowledge by ID (and related websites).
#     """
#     logger.info(f"Deleting knowledge with ID {knowledge_id}")
#     knowledge = db.query(KnowledgeModel).filter(KnowledgeModel.id == knowledge_id).first()
#     if not knowledge:
#         raise HTTPException(status_code=404, detail="Knowledge not found")
#
#     # Delete related websites
#     db.query(Website).filter(Website.knowledge_id == knowledge_id).delete()
#
#     # Delete knowledge
#     db.delete(knowledge)
#     db.commit()
#
#     return {
#         "status": 200,
#         "message": f"Knowledge with ID {knowledge_id} deleted successfully."
#     }