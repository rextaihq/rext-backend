from fastapi import APIRouter, Depends, HTTPException, status, Request
from src.api.schema.user_schema import LoginUser, RegisterUser
from src.utils.helper import hash_password, create_access_token, verify_password, create_refresh_token
from sqlalchemy.orm import Session
from src.api.models.user_models import User
from src.api.database.database import get_db
from src.utils.response_utils import success, error, created, unauthorized
from src.api.schema.response_schemas import ErrorCode, ErrorSeverity
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException,
    WrextValidationException
)
from dotenv import load_dotenv
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
        users = db.query(User).all()

        # Convert users to dict format (excluding passwords)
        user_data = [
            {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat() if hasattr(user, 'created_at') else None
            }
            for user in users
        ]

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
        existing_user = db.query(User).filter(
            (User.email == user.email) | (User.username == user.username)
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
        db_user = User(
            username=user.username,
            email=user.email,
            password=hashed_pwd
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Return user data (excluding password)
        user_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "created_at": db_user.created_at.isoformat() if hasattr(db_user, 'created_at') else None
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
    Endpoint to log in a user.
    """
    try:
        # Find user by email
        db_user = db.query(User).filter(User.email == user.email).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )

        # Verify password
        is_match = verify_password(password=user.password, hashed_password=db_user.password)
        if not is_match:
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": user.email}
            )

        # Prepare JWT payload
        token_data = {
            "sub": str(db_user.id),  # user id
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
                    "email": db_user.email
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

# @router.post("/refresh")
# def refresh_token(refresh_token: str = Body(..., embed=True)):
#     """
#     Refresh access token using refresh token.
#     """
#     payload = verify_token(refresh_token, REFRESH_SECRET_KEY)
#     user_id = payload.get("sub")

#     if not user_id:
#         raise HTTPException(status_code=401, detail="Invalid refresh token")

#     # create new access token
#     new_access_token = create_access_token(data={
#         "sub": user_id,
#         "username": payload.get("username"),
#         "email": payload.get("email"),
#     })

#     return {
#         "access_token": new_access_token,
#         "token_type": "bearer"
#     }