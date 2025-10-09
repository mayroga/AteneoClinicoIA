from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# Esquema base de usuario
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

# Crear usuario
class UserCreate(UserBase):
    password: str
    role: str  # "volunteer" o "clinician"

# Respuesta de usuario
class UserResponse(UserBase):
    id: int
    is_active: bool
    role: str
    created_at: datetime

    class Config:
        orm_mode = True

# Esquema base de caso clínico
class CaseBase(BaseModel):
    title: str
    description: Optional[str] = None
    level: str = "basic"  # basic, medium, advanced

# Crear caso
class CaseCreate(CaseBase):
    volunteer_id: Optional[int] = None
    assigned_to_id: Optional[int] = None

# Respuesta de caso
class CaseResponse(CaseBase):
    id: int
    status: str
    volunteer_id: Optional[int] = None
    assigned_to_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
