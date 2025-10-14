from pydantic import BaseModel
from typing import Optional

class RegisterUser(BaseModel):
    username: str
    email: str
    phone: str
    password: str
    date_of_birth: str

class LoginUser(BaseModel):
    username: str
    password: str

class UpdateUser(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None

class Location(BaseModel):
    label: str
    latitude: float
    longitude: float
    is_primary: bool = False
