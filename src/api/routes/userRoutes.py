from fastapi import APIRouter, HTTPException,Depends
from src.api.schema.userSchema import RegisterUser,LoginUser
from sqlalchemy.orm import Session
from src.api.models.models import User
from src.api.database.database import get_db


router = APIRouter(
    prefix="/user",
    tags=["user"]
)

@router.get("/status")
def get_user_status():
    """
    Endpoint to check the user service status.
    """
    return {"status": "running"}

@router.get("/users")
def get_users(db: Session = Depends(get_db)):
    """
    Endpoint to retrieve all users.
    """
    users = db.query(User).all()
    return {"users": users}


@router.post("/register")
def create_user(user: RegisterUser, db: Session = Depends(get_db)):
    """
    Endpoint to create a new user.
    """
    db_user = User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {
        "message": "User created successfully.",
        "user": db_user
    }


@router.post("/login")
def login_user(user: LoginUser):
    """
    Endpoint to log in a user.
    """
    # Here you would typically verify the user's credentials against your database
    # For now, we will just return a success message as a placeholder
    return {
        "message": "User logged in successfully.",
        "user": user
    }