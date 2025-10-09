from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from database import get_db
from models import User
from pydantic import BaseModel
import datetime

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Schemas
class RegisterUser(BaseModel):
    email: str
    password: str
    role: str  # 'volunteer' o 'professional'
    waiver_signed: bool

class LoginUser(BaseModel):
    email: str
    password: str

# Funciones auxiliares
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Registro
@router.post("/register")
def register(user: RegisterUser, db: Session = Depends(get_db)):
    if not user.waiver_signed:
        raise HTTPException(status_code=400, detail="Debe aceptar el waiver legal.")
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")
    
    new_user = User(
        email=user.email,
        hashed_password=hash_password(user.password),
        role=user.role,
        waiver_signed=user.waiver_signed,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Usuario registrado correctamente", "user_id": new_user.id}

# Login
@router.post("/login")
def login(user: LoginUser, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    return {"message": "Login exitoso", "user_id": db_user.id, "role": db_user.role}

# Verificación de waiver
@router.get("/waiver-status/{user_id}")
def waiver_status(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"waiver_signed": db_user.waiver_signed}
