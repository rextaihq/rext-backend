from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class RegisterUser(BaseModel):
    first_name: str = Field(..., description="First name of the user")
    last_name:  str = Field(..., description="Last name of the user")
    username:  str = Field(..., description="Name of the user")
    email: EmailStr = Field(..., description="Email address of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class LoginUser(BaseModel):
    email: EmailStr = Field(..., description="email of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class UpdateUser(BaseModel):
    email: Optional[EmailStr] = Field(None, description="User email")
    username: Optional[str] = Field(None, description="Username")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    display_name: Optional[str] = Field(None, description="Display name")
    password: Optional[str] = Field(None, description="Password (will be hashed)")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    language: Optional[str] = Field(None, description="User language")
    timezone: Optional[str] = Field(None, description="User timezone")

class ResetPassword(BaseModel):
    token: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address to send password reset link")