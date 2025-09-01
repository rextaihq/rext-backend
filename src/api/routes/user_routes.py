from fastapi import APIRouter,Depends,HTTPException, status
from src.api.schema.user_schema import LoginUser,RegisterUser
from src.utils.helper import hash_password,create_access_token,verify_password,create_refresh_token
from sqlalchemy.orm import Session
from src.api.models.models import User
from src.api.database.database import get_db
from dotenv import load_dotenv
import bcrypt
import jwt
import  os

load_dotenv()

SECRET_KEY= os.getenv("SECRET_KEY")
ALGORITHM= os.getenv("ALGORITHM")
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
    hashed_pwd = hash_password(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        password=hashed_pwd
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {
        "message": "User created successfully.",
        "user": db_user
    }


@router.post("/login")
def login_user(user: LoginUser, db: Session = Depends(get_db)):
    """
    Endpoint to log in a user.
    """
    db_user = db.query(User).filter(User.email == user.email).first()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    is_match = verify_password(password=user.password,hashed_password=db_user.password)
    if not is_match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password"
        )

    # Prepare JWT payload
    data = {
        "sub": str(db_user.id),  # user id
        "username": db_user.username,
        "email": db_user.email
    }

    token = create_access_token(data=data)
    refresh_token = create_refresh_token(data=data)

    return {
        "message": "User logged in successfully.",
        "access_token": token,
        "refresh_token": refresh_token, 
        "token_type": "bearer"
    }

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