from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Annotated, Optional
import json

from config import settings
from database import insert_waiver, insert_professional, get_user_type, get_professional_profile

# Router para manejar las rutas de autenticación
router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])

# --- Modelos Pydantic para la validación de datos ---

class WaiverRequest(BaseModel):
    """Modelo para la solicitud de firma del waiver inicial."""
    email: EmailStr
    user_type: Literal['volunteer', 'professional'] = Field(
        ..., 
        description="Tipo de usuario: 'volunteer' o 'professional'"
    )

class ProfessionalProfile(BaseModel):
    """Modelo para la creación o actualización del perfil del profesional."""
    email: EmailStr
    name: str = Field(..., min_length=2)
    specialty: str = Field(..., min_length=3)

# --- Dependencias de Autenticación ---

class AuthResult(BaseModel):
    """Resultado de la verificación de autenticación, usado por Depends."""
    email: EmailStr
    user_type: str
    is_admin: bool

async def get_current_user(email: str = Depends(lambda e: e)) -> AuthResult:
    """
    Dependencia de ejemplo para obtener el usuario actual a partir de un email.
    En una aplicación real, esto validaría un token JWT. Aquí solo verifica el waiver.
    
    Nota: La dependencia se simplifica aquí. En el main.py, otras rutas usarían
    esta dependencia para verificar el email en los headers o cookies.
    """
    # 1. Verificar si el email ha firmado el waiver
    user_type = get_user_type(email)
    if not user_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no registrado. Debe firmar el waiver primero."
        )

    # 2. Verificar si el usuario es un administrador usando el bypass key
    is_admin = False
    # Podríamos verificar aquí si el email coincide con un admin predefinido
    # o si se proporciona la ADMIN_BYPASS_KEY en un header/query param
    # Por ahora, solo usamos el tipo de usuario.

    return AuthResult(email=email, user_type=user_type, is_admin=is_admin)

# --- ENDPOINTS de Autenticación ---

@router.post("/waiver", status_code=status.HTTP_201_CREATED)
def sign_waiver(data: WaiverRequest):
    """
    Paso 1: Firma legal del waiver. Es un paso obligatorio para registrarse
    como 'volunteer' o 'professional'.
    """
    success = insert_waiver(data.email, data.user_type)
    if not success:
        # Esto ocurre si el email ya existe o hay un error de DB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error al registrar o el email ya está en uso."
        )
    
    return {"message": f"Waiver firmado con éxito. Tipo de usuario: {data.user_type}"}

@router.post("/professional/profile", status_code=status.HTTP_201_CREATED)
def create_professional_profile(data: ProfessionalProfile):
    """
    Crea o actualiza el perfil detallado del profesional (nombre, especialidad).
    Requiere que el usuario ya haya firmado el waiver como 'professional'.
    """
    # Verificación de tipo de usuario para asegurar que solo los profesionales creen este perfil
    user_type = get_user_type(data.email)
    if user_type != 'professional':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los usuarios tipo 'professional' pueden crear este perfil."
        )
        
    success = insert_professional(data.email, data.name, data.specialty)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear el perfil del profesional."
        )
        
    return {"message": "Perfil de profesional creado/actualizado con éxito."}

@router.get("/me", response_model=AuthResult)
def get_user_status(email: str):
    """
    Verifica el estado de un usuario (tipo, perfil de profesional si aplica).
    Esta ruta simula la verificación de identidad después de que se proporciona un email.
    """
    auth_data = get_current_user(email)
    
    response = auth_data.model_dump()
    
    if auth_data.user_type == 'professional':
        profile = get_professional_profile(auth_data.email)
        if profile:
            # Añadir créditos y ranking al estado del usuario si es profesional
            response['credits'] = profile['credits']
            response['score_refutation'] = profile['score_refutation']
        else:
             response['warning'] = "Perfil de profesional no completado. Por favor, crea tu perfil."

    return response
