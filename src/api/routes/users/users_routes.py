from fastapi import APIRouter, Depends, HTTPException, status, Request
from src.api.schema.user_schema import LoginUser, RegisterUser,UpdateUser
from src.utils.helper import hash_password, create_access_token, verify_password, create_refresh_token
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created, unauthorized
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException,
    WrextValidationException
)
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

load_dotenv()

SECRET_KEY= os.getenv("SECRET_KEY")
ALGORITHM= os.getenv("ALGORITHM")
router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.get("/status")
def get_user_status(request: Request):
    """
    Endpoint to check the user service status.
    """
    return success(
        data={"status": "running", "service": "user_service"},
        request=request,
        message="User service is operational"
    )

@router.get("/users")
def get_users(request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to retrieve all users.
    """
    try:
        users = db.query(Users).all()

        # Convert users to dict format (excluding passwords)
        user_data = [user.to_dict() for user in users]

        return success(
            data={"users": user_data, "total_count": len(user_data)},
            request=request,
            message=f"Retrieved {len(user_data)} users successfully"
        )
    except Exception as e:
        return error(
            message="Failed to retrieve users",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            request=request
        )


@router.post("/register")
def create_user(user: RegisterUser, request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to create a new user.
    """
    try:
        # Check if user already exists with this email
        existing_user = db.query(Users).filter(
            (Users.email == user.email)
        ).first()

        if existing_user:
            if existing_user.email == user.email:
                raise DuplicateResourceException(
                    message="A user with this email already exists",
                    resource_type="user",
                    conflicting_field="email",
                    conflicting_value=user.email
                )
            else:
                raise DuplicateResourceException(
                    message="A user with this username already exists",
                    resource_type="user",
                    conflicting_field="username",
                    conflicting_value=user.username
                )

        # Hash password and create user
        hashed_pwd = hash_password(user.password)
        new_user = Users(
            username=user.username,
            email=user.email,
            password_hash=hashed_pwd
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # Return user data (excluding password)
        user_data = {
            "id": str(new_user.id),
            "username": new_user.username,
            "email": new_user.email,
            "status": new_user.status,
            "created_at": new_user.created_at.isoformat() if hasattr(new_user, 'created_at') else None
        }

        return created(
            data={"user": user_data},
            request=request,
            message="User created successfully"
        )

    except DuplicateResourceException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        db.rollback()
        return error(
            message="Failed to create user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )


@router.post("/login")
def login_user(user: LoginUser, request: Request, db: Session = Depends(get_db)):
    """
    Endpoint to log in a user with table updates.
    """
    try:
        # Find user by email
        db_user = db.query(Users).filter(Users.email == user.email).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )
        # Check if account is locked
        if db_user.locked_until and db_user.locked_until > datetime.utcnow():
            raise WrextAuthenticationException(
                message="Account is temporarily locked due to multiple failed login attempts. Please try again later.",
                context={"locked_until": db_user.locked_until.isoformat()}
            )
        
        # Verify password
        is_match = verify_password(password=user.password, hashed_password=db_user.password_hash)
        if not is_match:
            # increment failed login attempts
            db_user.failed_login_attempts = (db_user.failed_login_attempts or 0) + 1

            # lock account if too many failures
            if db_user.failed_login_attempts >= 3:
                db_user.locked_until = datetime.utcnow() + timedelta(hours=1) 

            db.commit()
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )

        # login
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.utcnow()
        db_user.login_count = (db_user.login_count or 0) + 1
        db.commit()
        db.refresh(db_user)

        # Prepare JWT payload
        token_data = {
            "sub": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        # Return successful login response
        return success(
            data={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "id": str(db_user.id),
                    "username": db_user.username,
                    "email": db_user.email,
                    "last_login_at": db_user.last_login_at,
                    "login_count": db_user.login_count
                }
            },
            request=request,
            message="User logged in successfully"
        )

    except WrextAuthenticationException:
        # Re-raise to be handled by middleware
        raise
    except Exception as e:
        return error(
            message="Login failed due to server error",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )

# Delete user
@router.delete("/delete/{user_id}")
def delete_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Soft delete a user by setting deleted_at timestamp
    """
    try:
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Soft delete
        db_user.deleted_at = datetime.utcnow()
        db.commit()

        return success(
            data={"id": str(db_user.id)},
            request=request,
            message="User deleted successfully"
        )

    except Exception as e:
        db.rollback()
        return error(
            message="Failed to delete user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )

# update user details
@router.put("/update/{user_id}")
def update_user(user_id: str, user: UpdateUser, request: Request, db: Session = Depends(get_db)):
    """
    Update user details
    """
    try:
        db_user = db.query(Users).filter(Users.id == user_id).first()
        if not db_user:
            return error(
                message="User not found",
                code=ErrorCode.NOT_FOUND,
                status_code=404,
                severity=ErrorSeverity.MEDIUM,
                request=request
            )

        # Update fields if provided
        if user.email is not None:
            db_user.email = user.email
        if user.username is not None:
            db_user.username = user.username
        if user.first_name is not None:
            db_user.first_name = user.first_name
        if user.last_name is not None:
            db_user.last_name = user.last_name
        if user.display_name is not None:
            db_user.display_name = user.display_name
        if user.language is not None:
            db_user.language = user.language
        if user.timezone is not None:
            db_user.timezone = user.timezone

        db.commit()
        db.refresh(db_user)

        # Return updated user data (excluding password)
        user_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "display_name": db_user.display_name,
            "language": db_user.language,
            "timezone": db_user.timezone,
            "status": db_user.status,
            "updated_at": db_user.updated_at.isoformat() if hasattr(db_user, 'updated_at') else None
        }

        return success(
            data={"user": user_data},
            request=request,
            message="User updated successfully"
        )

    except Exception as e:
        db.rollback()
        return error(
            message="Failed to update user",
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            status_code=500,
            severity=ErrorSeverity.HIGH,
            context={"error_details": str(e)},
            request=request
        )