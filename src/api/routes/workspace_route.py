from fastapi import (
    APIRouter, Depends,
    HTTPException,
)
from src.utils.logger import logger
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.models.workspace_model import WorkspaceModel
from src.nodes.vectorStore.buildVectorStore import build_vector_store
from src.api.models.knowledge_model import BrandVoice
from src.api.schema.knowledge_schema import BrandSchema
from src.model.model import load_model
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from src.utils.helper import web_page_scraper


router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    responses={404: {"description": "Not found"}},
)


# Health Check
@router.get("/")
def get_status():
    logger.info("Knowledge Route health check called.")
    return {"status": "Knowledge Route is working!"}


# get workspaces
@router.get("/all")
def get_workspaces(
    db: Session = Depends(get_db)
):
    workspaces = db.query(WorkspaceModel).all()
    return {
        "status": 200,
        "workspaces": [
            {
                "id": str(ws.id),
                "title": ws.title,
                "description": ws.description,
                "url": ws.url,
            } for ws in workspaces
        ]
    }

# get by id
@router.get("/{workspace_id}")
def get_workspace_by_id(
    workspace_id: str,
    db: Session = Depends(get_db)
):
    workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
    if not workspace:
        logger.warning(f"Workspace not found: {workspace_id}")
        raise HTTPException(status_code=404, detail="Workspace not found")

    return {
        "status": 200,
        "workspace": {
            "id": str(workspace.id),
            "title": workspace.title,
            "description": workspace.description,
            "url": workspace.url,
        }
    }

# CREATE Workspace
@router.post("/create")
async def create_knowledge(
    data: WorkspaceSchema,
    db: Session = Depends(get_db)
):
    logger.info(f"Received request to create workspace: {data.title}")

    # Check duplicate
    existing_workspace = db.query(WorkspaceModel).filter_by(title=data.title).first()
    if existing_workspace:
        logger.warning(f"Duplicate workspace title: {data.title}")
        raise HTTPException(
            status_code=400,
            detail=f"Workspace with title '{data.title}' already exists."
        )

    try:
        # Scrape website
        logger.info(f"Scraping content from: {data.url}")
        chunks, results = await web_page_scraper(urls=[data.url])
        result = results[0]
        if not result.success:
            logger.error(f"Failed to scrape URL: {data.url}")
            raise HTTPException(status_code=422, detail="Failed to scrape the provided URL")

        content = result.markdown

        # Create workspace record first
        workspace = WorkspaceModel(
                title=data.title,
                description=getattr(data, "description", None),
                url=str(data.url),
            )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        logger.info(f"Workspace created with id={workspace.id}")

        # Push scraped chunks into vector store
        try:
            logger.info(f"Inserting {len(chunks)} chunks into vector store for {result.url}")
            build_vector_store(blog_context=chunks)
        except Exception as vec_err:
            logger.exception("Vector store insertion failed")
            # Continue workflow – don't block workspace creation
            raise HTTPException(status_code=500, detail="Vector store error")

        # Extract brand info using LLM
        try:
            logger.info("Extracting brand voice using LLM")
            model = load_model()
            structure_model = model.with_structured_output(BrandSchema)
            brand_data = structure_model.invoke(content)
            logger.info(f"Content get: {brand_data}")

            brand_voice = BrandVoice(
                workspace_id=workspace.id,
                about=brand_data.about,
                customer_profile=brand_data.customer_profile,
                selling_position=brand_data.selling_position,
                target_audience=brand_data.target_audience,
                brand_voice=brand_data.brand_voice,
                competitors=brand_data.competitors,
                content_strategy=brand_data.content_pillar,
            )

            db.add(brand_voice)
            db.commit()
            db.refresh(brand_voice)

            logger.info(f"Brand voice saved for workspace {workspace.id}")
        except Exception as llm_err:
            logger.exception("LLM extraction failed")
            # Workspace is still valid – don't fail entire request
            raise HTTPException(status_code=500, detail="Failed to extract brand voice")

        return {
            "status": 200,
            "message": "Workspace created successfully",
            "workspace": {
                "id": str(workspace.id),
                "title": workspace.title,
                "description": workspace.description,
                "url": workspace.url,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error creating workspace {data.title}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Delete
@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    db: Session = Depends(get_db)
):
    logger.info(f"Received request to delete workspace: {workspace_id}")

    workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
    if not workspace:
        logger.warning(f"Workspace not found: {workspace_id}")
        raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        db.delete(workspace)
        db.commit()
        logger.info(f"Workspace deleted: {workspace_id}")
        return {
            "status": 200,
            "message": "Workspace deleted successfully"
        }
    except Exception as e:
        logger.exception(f"Error deleting workspace {workspace_id}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# update
@router.put("/{workspace_id}")
def update_workspace(
    workspace_id: str,
    data: WorkspaceSchema,
    db: Session = Depends(get_db)
):
    logger.info(f"Received request to update workspace: {workspace_id}")

    workspace = db.query(WorkspaceModel).filter_by(id=workspace_id).first()
    if not workspace:
        logger.warning(f"Workspace not found: {workspace_id}")
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Check for duplicate title if title is being updated
    if data.title and data.title != workspace.title:
        existing_workspace = db.query(WorkspaceModel).filter_by(title=data.title).first()
        if existing_workspace:
            logger.warning(f"Duplicate workspace title: {data.title}")
            raise HTTPException(
                status_code=400,
                detail=f"Workspace with title '{data.title}' already exists."
            )

    try:
        # Update fields
        if data.title:
            workspace.title = data.title
        if data.description is not None:
            workspace.description = data.description
        if data.url:
            workspace.url = str(data.url)

        db.commit()
        db.refresh(workspace)
        logger.info(f"Workspace updated: {workspace_id}")

        return {
            "status": 200,
            "message": "Workspace updated successfully",
            "workspace": {
                "id": str(workspace.id),
                "title": workspace.title,
                "description": workspace.description,
                "url": workspace.url,
            }
        }
    except Exception as e:
        logger.exception(f"Error updating workspace {workspace_id}")
        raise HTTPException(status_code=500, detail="Internal Server Error")