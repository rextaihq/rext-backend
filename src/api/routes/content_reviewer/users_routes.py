from fastapi import (
    APIRouter, Depends, Request,
)
from src.utils.logger import logger
from sqlalchemy.orm import Session
from src.api.models.users_model import ContentUsers
from src.api.schema.users_schema import UsersBase
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
    prefix="/content-users",
    tags=["Content Users"],
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

# get all User
@router.get("/users")
def get_all_users(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        users = db.query(ContentUsers).all()
        
        users_data = [
            user.to_dict() for user in users
        ]
        return success(
            data=users_data,
            request=request,
            message="Users fetched successfully."
        )
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while fetching users.",
            request=request
        )

# get by id
@router.get("/user/{user_id}")
def get_user_by_id(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(ContentUsers).filter(ContentUsers.id == user_id).first()
        if not user:
            raise ResourceNotFoundException(f"User with id {user_id} not found.")
        return success(
            data=user.to_dict(),
            request=request,
            message="User fetched successfully."
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
        logger.error(f"Error fetching users: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while fetching the users.",
            request=request
        )
    
# create user
@router.post("/add-user")
def create_user(
    request: Request,
    data:UsersBase,
    db: Session = Depends(get_db)
):
    try:
        # Check for duplicate email
        existing_user = db.query(ContentUsers).filter(ContentUsers.email == data.email).first()
        if existing_user:
            raise DuplicateResourceException(f"User with email {data.email} already exists.")
        
        new_user = ContentUsers(
            name=data.name,
            email=data.email,
            expertise=data.expertise,
            affiliated_topics=data.affiliated_topics
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return created(
            data=new_user.to_dict(),
            request=request,
            message="new_user created successfully."
        )
    except DuplicateResourceException as dre:
        logger.warning(f"Duplicate resource: {dre}")
        return error(
            message="Users with this email already exists.",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return error(
            message="Failed to add user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )
    

# update user
@router.put("/update-user/{user_id}")
def update_user(
    request: Request,
    user_id: str,
    data:UsersBase,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(ContentUsers).filter(ContentUsers.id == user_id).first()
        if not user:
            raise ResourceNotFoundException(f"User with id {user_id} not found.")
        
        # Update fields
        user.name = data.name
        user.email = data.email
        user.expertise = data.expertise
        user.affiliated_topics = data.affiliated_topics
        
        db.commit()
        db.refresh(user)
        return success(
            data=user.to_dict(),
            request=request,
            message="User updated successfully."
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
        logger.error(f"Error updating User: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while updating the User",
            request=request
        )

# delete User
@router.delete("/delete-user/{user_id}")
def delete_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db)
):
    try:
        user = db.query(ContentUsers).filter(ContentUsers.id == user_id).first()
        if not user:
            raise ResourceNotFoundException(f"user with id {user_id} not found.")
        
        db.delete(user)
        db.commit()
        return success(
            data=None,
            request=request,
            message="user deleted successfully."
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
        logger.error(f"Error deleting user: {e}")
        return error(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            error_severity=ErrorSeverity.HIGH,
            message="An error occurred while deleting the user.",
            request=request
        )