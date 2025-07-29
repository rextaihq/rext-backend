from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional

class RegisterUser(BaseModel):
    name: str = Field(..., description="Name of the user")
    email: str = Field(..., description="Email address of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")


class LoginUser(BaseModel):
    username: str = Field(..., description="Username of the user")
    password: str = Field(..., min_length=8, description="Password for the user account")