from fastapi import (
    APIRouter,Depends,
    HTTPException,
    UploadFile, File, 
    Form,BackgroundTasks
    )
from src.api.tasks.project_task import project_task
from src.utils.logger import logger
from src.api.models.projects_model import Projects
from sqlalchemy.orm import Session
from src.api.database.database import get_db
from typing import List
import os, shutil, mimetypes
from uuid import uuid4

router = APIRouter(
    prefix="/projects",
    tags=["projects"]
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/")
def get_status():
    logger.info("Projects Route health check called.")
    return {"status": "Projects Route is working!"}


# get projects
@router.get("/get-projects")
def get_projects(db: Session = Depends(get_db)):
    try:
        logger.info("Get projects endpoint called.")
        projects = db.query(Projects).all()
        project_list = [
            {
                "id": project.id,
                "title": project.title,
                "description": project.description,
                "instructions": project.instructions
            }
            for project in projects
        ]
        logger.info(f"Fetched {len(project_list)} projects.")
        return project_list
    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# create
@router.post("/create-project")
def create_project(
    title: str = Form(..., max_length=80, description="Title of the project"),
    memory_mode: bool = Form(False, description="Enable or disable memory mode"),
    instructions: List[str] = Form(..., description="List of instructions for the project"),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    try:
        logger.info("Create project endpoint called.")
        file_attachments = []
        projects = []

        if files:
            for file in files:
                ext = os.path.splitext(file.filename)[1]
                if ext not in [".pdf", ".csv", ".txt"]:
                    logger.warning(f"Unsupported file type: {ext}")
                    raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
                     
                unique_name = f"{uuid4()}{ext}"
                file_path = os.path.join(UPLOAD_DIR, unique_name)

                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                file_url = f"/static/{unique_name}"  # serve via StaticFiles
                filetype = mimetypes.guess_type(file.filename)[0] or "unknown"

                file_attachments.append({
                    "filename": file.filename,
                    "url": file_url,
                    "path": file_path,  # keep path for background task
                    "filetype": filetype
                })

        # create project in DB
        project = Projects(
            title=title,
            memory_mode=str(memory_mode).lower(),
            instructions=instructions,
            file=file_attachments if file_attachments else None,
            status="process"
        )

        db.add(project)
        db.commit()
        db.refresh(project)
        logger.info(f"Project created with ID: {project.id}")
        projects.append(project)

        # ✅ add background task
        if file_attachments:
            for f in file_attachments:
                background_tasks.add_task(project_task, f["path"], project.id)

        return {
            "status": "success",
            "project": project
        }

    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/get-project/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    try:
        logger.info(f"Get project endpoint called for project_id: {project_id}")
        project = db.query(Projects).filter(Projects.id == project_id).first()
        if not project:
            logger.warning(f"Project with ID {project_id} not found.")
            raise HTTPException(status_code=404, detail="Project not found")
        
        logger.info(f"Project with ID {project_id} fetched successfully.")
        return {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "instructions": project.instructions
        }

    except Exception as e:
        logger.error(f"Error fetching project: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# delete
@router.delete("/delete-project/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    try:
        logger.info(f"Delete project endpoint called for project_id: {project_id}")
        project = db.query(Projects).filter(Projects.id == project_id).first()
        if not project:
            logger.warning(f"Project with ID {project_id} not found.")
            raise HTTPException(status_code=404, detail="Project not found")
        
        db.delete(project)
        db.commit()
        logger.info(f"Project with ID {project_id} deleted successfully.")
        return {
            "status": "success",
            "message": f"Project {project_id} deleted successfully."
        }
    except Exception as e:
        logger.error(f"Error deleting project: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")