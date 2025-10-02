from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Annotated, Optional
import json

from config import settings
# ----------------------------------------------------------------------
# ¡CAMBIO CLAVE AQUÍ!
# Nombres de funciones corregidos para que coincidan con database.py:
# - insert_waiver  -> sign_waiver
# - insert_professional -> create_profile (que maneja ambos tipos)
# - get_user_type  -> get_profile_by_email (que devuelve el perfil completo)
# ----------------------------------------------------------------------
from database import sign_waiver, create_profile, get_profile_by_email, get_professional_profile

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
    # Añadimos Optional para los datos que solo tienen los profesionales
    credits: Optional[int] = None
    ranking_score: Optional[int] = None
    warning: Optional[str] = None

async def get_current_user(email: str = Depends(lambda e: e)) -> AuthResult:
    """
    Dependencia para obtener el usuario actual. En una app real validaría un token.
    """
    # Usamos la función corregida para obtener el perfil completo
    profile = get_profile_by_email(email)
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no registrado. Debe firmar el waiver primero."
        )

    # El user_type y si el waiver está firmado se obtienen del perfil
    user_type = profile.get('user_type')
    is_waiver_signed = profile.get('is_waiver_signed', False)
    
    # Podrías querer forzar el waiver aquí, si no está firmado:
    if not is_waiver_signed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Waiver no firmado. Por favor, complete el registro legal."
        )

    # 2. Asignar is_admin (simplificado)
    is_admin = False 

    return AuthResult(email=email, user_type=user_type, is_admin=is_admin)

# --- ENDPOINTS de Autenticación ---

@router.post("/waiver", status_code=status.HTTP_201_CREATED)
def sign_waiver_endpoint(data: WaiverRequest):
    """
    Paso 1: Firma legal del waiver. Es un paso obligatorio para registrarse.
    """
    # 1. Intentar crear el perfil (professional o volunteer)
    # Usamos create_profile, que inserta el perfil base si no existe.
    profile_created = create_profile(data.email, data.user_type)
    
    # 2. Firmar el waiver. Usamos la función correcta: sign_waiver.
    # Esta función actualizará el campo is_waiver_signed a TRUE.
    waiver_signed = sign_waiver(data.email)
    
    if not profile_created or not waiver_signed:
        # Esto ocurre si hay un error de DB o si el create_profile falla por algún motivo
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error en la base de datos al registrar o firmar el waiver."
        )
    
    return {"message": f"Waiver firmado con éxito. Tipo de usuario: {data.user_type}"}

@router.post("/professional/profile", status_code=status.HTTP_201_CREATED)
def create_professional_detail_profile(data: ProfessionalProfile):
    """
    Crea o actualiza el perfil detallado del profesional (nombre, especialidad).
    Esta función asume que ya existe un perfil en la tabla 'profiles'.
    """
    # Usamos la función corregida
    profile_data = get_profile_by_email(data.email)
    
    # Verificación de tipo de usuario
    if not profile_data or profile_data.get('user_type') != 'professional':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los usuarios tipo 'professional' registrados pueden crear este perfil."
        )
        
    # FIX PENDIENTE: Tu archivo database.py NO tiene la función
    # 'insert_professional'. Si esta función solo actualiza el ranking/créditos,
    # el endpoint podría no hacer nada. Debes crear una función en database.py
    # para actualizar los campos 'name' y 'specialty' del perfil.
    
    # Usaremos una función de placeholder temporal, ¡PERO DEBES CREARLA!
    # success = update_professional_details(data.email, data.name, data.specialty) 
    
    # Por ahora, para que compile, eliminaremos la llamada a la función que falta.
    # Si la función real es insert_professional, su implementación DEBE estar en database.py.
    
    # if not success:
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail="Error al crear el perfil del profesional."
    #     )
        
    # return {"message": "Perfil de profesional creado/actualizado con éxito."}
    
    # Temporalmente levantamos una excepción para avisar que la DB no soporta esta función
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="La funcionalidad de actualizar detalles de perfil profesional aún no está implementada en la base de datos (función 'insert_professional' faltante)."
    )


@router.get("/me", response_model=AuthResult)
def get_user_status(current_user: AuthResult = Depends(get_current_user)):
    """
    Obtiene el estado del usuario actual (tipo, créditos, ranking).
    """
    # Eliminamos el parámetro 'email: str' ya que la dependencia lo maneja.
    
    response_data = current_user.model_dump()
    
    if current_user.user_type == 'professional':
        # Esta función SI existe en database.py
        profile = get_professional_profile(current_user.email)
        
        if profile:
            # Añadir créditos y ranking al estado del usuario si es profesional
            response_data['credits'] = profile.get('credits')
            response_data['ranking_score'] = profile.get('ranking_score') # Corregido a 'ranking_score'
        else:
            # Este caso es improbable si get_current_user ya pasó, 
            # pero es buena práctica cubrirlo.
            response_data['warning'] = "Datos de profesional faltantes. Por favor, revise su perfil."

    return response_data
