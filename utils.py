# utils.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

# Importaciones de terceros
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

# 🛑 Importaciones de sus módulos locales
# Asumimos que get_db está en database.py y el modelo User está en models.py
from database import get_db
from models import User  # Asumimos que el modelo SQLAlchemy se llama 'User'

# 1. Configuración de Variables de Entorno (desde Render)
# ----------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY")
ADMIN_BYPASS_KEY = os.environ.get("ADMIN_BYPASS_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
RENDER_APP_URL = os.environ.get("RENDER_APP_URL")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
CARGO_HOME = os.environ.get("CARGO_HOME")
EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")

# Configuración de JWT y Hashing
ALGORITHM = "HS256"
# Tiempo de expiración ajustado a 24 horas (60 minutos * 24 horas)
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 

# Contexto de passlib para hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Esquema para inyección de dependencia
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token") 


# ----------------------------------------------------------------------
# 2. Funciones de Contraseña y Token
# ----------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Genera un hash seguro para la contraseña."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si una contraseña plana coincide con el hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token de acceso JWT.
    Asume que data['email'] se pasa como el identificador único (sub).
    """
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY no está configurada. El token no puede ser firmado.")

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # El identificador único (email) se usa como 'sub' (subject)
    to_encode.update({"exp": expire, "sub": to_encode.get("email")}) 
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ----------------------------------------------------------------------
# 3. Integración de Base de Datos y Guardianes de Acceso (Dependencies)
# ----------------------------------------------------------------------

def get_user_from_db(db: Session, email: str) -> Optional[User]:
    """Busca el usuario en la base de datos por email."""
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalars().first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """
    Función clave de seguridad. Valida el JWT y obtiene el objeto Usuario de SQLAlchemy.
    """
    if not SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de configuración del servidor: SECRET_KEY faltante.",
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales no válidas o token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decodificación del token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # El identificador único (email) se extrae del campo 'sub'
        email: str = payload.get("sub") 
        
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Obtener el objeto User de la DB
    user = get_user_from_db(db, email=email)
    if user is None:
        raise credentials_exception
    
    # Retorna el objeto del modelo User (tipado limpio)
    return user


def get_admin_for_unlimited_access(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependencia de Autorización. Verifica el rol 'admin' para acceso ilimitado.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso prohibido. Se requiere rol de administrador.",
        )
    return current_user


def get_current_volunteer(current_user: User = Depends(get_current_user)) -> User:
    """Dependencia que requiere el rol 'volunteer' o 'admin'."""
    if current_user.role not in ["volunteer", "admin"]: 
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso prohibido. Se requiere rol de voluntario.",
        )
    return current_user

# ----------------------------------------------------------------------
# Fin de utils.py
# ----------------------------------------------------------------------
