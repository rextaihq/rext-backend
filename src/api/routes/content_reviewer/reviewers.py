from fastapi import (
    APIRouter, Depends, Request,
)
from src.utils.logger import logger
from sqlalchemy.orm import Session
from src.api.models.reviewser_model import ContentReviewer
from src.api.schema.reviwer_schema import ReviewerBase
from src.api.security.auth import get_api_key, API_KEY
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    WrextExternalServiceException,
    WrextValidationException,
    WrextAuthenticationException
)
from datetime import datetime, timezone



router = APIRouter(
    prefix="/content-reviewer",
    tags=["Content Reviewer"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(get_api_key)]
)

@router.get("/")
def read_root(
    request: Request
):
    logger.info("Workspace Route health check called.")
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is working!"
    )

# get all reviewers
@router.get("/reviewers")
def get_all_reviewers(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        reviewers = db.query(ContentReviewer).all()
        
        reviwer_data = [
            reviewer.to_dict() for reviewer in reviewers
        ]
        return success(
            data=reviwer_data,
            request=request,
            message="Reviewers fetched successfully."
        )
    except Exception as e:
        logger.error(f"Error fetching reviewers: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while fetching reviewers.",
            request=request
        )

# get by id
@router.get("/reviewer/{reviewer_id}")
def get_reviewer_by_id(
    request: Request,
    reviewer_id: str,
    db: Session = Depends(get_db)
):
    try:
        reviewer = db.query(ContentReviewer).filter(ContentReviewer.id == reviewer_id).first()
        if not reviewer:
            raise ResourceNotFoundException(f"Reviewer with id {reviewer_id} not found.")
        return success(
            data=reviewer.to_dict(),
            request=request,
            message="Reviewer fetched successfully."
        )
    except ResourceNotFoundException as rnfe:
        logger.warning(f"Resource not found: {rnfe}")
        return error(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            error_severity=ErrorSeverity.MEDIUM,
            message=str(rnfe),
            request=request
        )
    except Exception as e:
        logger.error(f"Error fetching reviewer: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while fetching the reviewer.",
            request=request
        )
    
# create reviewer
@router.post("/add-reviewer")
def create_reviewer(
    request: Request,
    data:ReviewerBase,
    db: Session = Depends(get_db)
):
    try:
        # Check for duplicate email
        existing_reviewer = db.query(ContentReviewer).filter(ContentReviewer.email == data.email).first()
        if existing_reviewer:
            raise DuplicateResourceException(f"Reviewer with email {data.email} already exists.")
        
        new_reviewer = ContentReviewer(
            name=data.name,
            email=data.email,
            expertise=data.expertise,
            affiliated_topics=data.affiliated_topics
        )
        db.add(new_reviewer)
        db.commit()
        db.refresh(new_reviewer)
        return created(
            data=new_reviewer.to_dict(),
            request=request,
            message="Reviewer created successfully."
        )
    except DuplicateResourceException as dre:
        logger.warning(f"Duplicate resource: {dre}")
        return error(
            message="Reviewer with this email already exists.",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
    except Exception as e:
        logger.error(f"Error creating reviewer: {e}")
        return error(
            message="Failed to add reviewer",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
    

# update reviewer
@router.put("/update-reviewer/{reviewer_id}")
def update_reviewer(
    request: Request,
    reviewer_id: str,
    data:ReviewerBase,
    db: Session = Depends(get_db)
):
    try:
        reviewer = db.query(ContentReviewer).filter(ContentReviewer.id == reviewer_id).first()
        if not reviewer:
            raise ResourceNotFoundException(f"Reviewer with id {reviewer_id} not found.")
        
        # Update fields
        reviewer.name = data.name
        reviewer.email = data.email
        reviewer.expertise = data.expertise
        reviewer.affiliated_topics = data.affiliated_topics
        
        db.commit()
        db.refresh(reviewer)
        return success(
            data=reviewer.to_dict(),
            request=request,
            message="Reviewer updated successfully."
        )
    except ResourceNotFoundException as rnfe:
        logger.warning(f"Resource not found: {rnfe}")
        return error(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            error_severity=ErrorSeverity.MEDIUM,
            message=str(rnfe),
            request=request
        )
    except Exception as e:
        logger.error(f"Error updating reviewer: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while updating the reviewer.",
            request=request
        )

# delete reviewer
@router.delete("/delete-reviewer/{reviewer_id}")
def delete_reviewer(
    request: Request,
    reviewer_id: str,
    db: Session = Depends(get_db)
):
    try:
        reviewer = db.query(ContentReviewer).filter(ContentReviewer.id == reviewer_id).first()
        if not reviewer:
            raise ResourceNotFoundException(f"Reviewer with id {reviewer_id} not found.")
        
        db.delete(reviewer)
        db.commit()
        return success(
            data=None,
            request=request,
            message="Reviewer deleted successfully."
        )
    except ResourceNotFoundException as rnfe:
        logger.warning(f"Resource not found: {rnfe}")
        return error(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            error_severity=ErrorSeverity.MEDIUM,
            message=str(rnfe),
            request=request
        )
    except Exception as e:
        logger.error(f"Error deleting reviewer: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while deleting the reviewer.",
            request=request
        )