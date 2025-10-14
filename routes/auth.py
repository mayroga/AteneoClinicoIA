from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from database import get_db
from models import User
from pydantic import BaseModel
import datetime
from config import ADMIN_BYPASS_KEY # Importamos la clave de administrador desde config

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =================================================================
# SCHEMAS
# =================================================================
class RegisterUser(BaseModel):
    email: str
    password: str
    role: str  # 'volunteer', 'professional', o 'admin'
    waiver_signed: bool

class LoginUser(BaseModel):
    email: str
    password: str

# =================================================================
# FUNCIONES AUXILIARES
# =================================================================
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# =================================================================
# 1. RUTA DE REGISTRO
# =================================================================
@router.post("/register")
def register(user: RegisterUser, db: Session = Depends(get_db)):
    if not user.waiver_signed and user.role != 'admin': # Admin no necesita waiver
        raise HTTPException(status_code=400, detail="Debe aceptar el waiver legal.")
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")
    
    new_user = User(
        email=user.email,
        hashed_password=hash_password(user.password),
        role=user.role,
        # Nota: Asume que 'waiver_signed' existe en el modelo User
        waiver_signed=user.waiver_signed,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Usuario registrado correctamente", "user_id": new_user.id}

# =================================================================
# 2. RUTA DE LOGIN ESTÁNDAR (Voluntario/Profesional)
# =================================================================
@router.post("/login")
def login(user: LoginUser, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    
    return {"message": "Login exitoso", "user_id": db_user.id, "role": db_user.role}

# =================================================================
# 3. RUTA DE LOGIN DE ADMINISTRADOR (CORREGIDA)
# =================================================================
@router.post("/admin")
def admin_login(
    user: LoginUser, 
    db: Session = Depends(get_db), 
    admin_secret_key: str = Header(None, alias="X-Admin-Key") # Captura el encabezado secreto
):
    # 💡 CORRECCIÓN: Usamos .strip() para sanear la clave de administrador
    if not admin_secret_key or admin_secret_key.strip() != ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=403, detail="Clave de administrador incorrecta o faltante.")

    # Verificación de credenciales estándar 
    db_user = db.query(User).filter(User.email == user.email, User.role == "admin").first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales de Administrador incorrectas.")

    # Si pasa ambas verificaciones, el acceso es otorgado
    return {
        "message": "Acceso de Administrador otorgado", 
        "user_id": db_user.id, 
        "role": "admin",
    }

# =================================================================
# 4. RUTA DE VERIFICACIÓN DE WAIVER
# =================================================================
@router.get("/waiver-status/{user_id}")
def waiver_status(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"waiver_signed": db_user.waiver_signed}
