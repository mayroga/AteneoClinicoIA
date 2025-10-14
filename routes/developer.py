from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
import json
import datetime
from database import get_db
from models import Case
from utils import get_current_user
from config import GEMINI_API_KEY
# 💡 CORRECCIÓN CLAVE: Usamos la importación explícita para el SDK de Gemini
from google.genai import Client, configure 

# =================================================================
# CONFIGURACIÓN DEL ROUTER
# =================================================================
router = APIRouter(prefix="/developer", tags=["developer"])

# La clave de Gemini se asume configurada en config.py
if GEMINI_API_KEY:
    try:
        # Inicialización del cliente Gemini para uso en la ruta (corregido)
        configure(api_key=GEMINI_API_KEY)
        gemini_client = Client() # Usamos el constructor Client importado directamente
        print("INFO: Cliente de Gemini configurado con éxito.")
    except Exception as e:
        # Mantener el manejo de errores original
        print(f"Error al inicializar cliente Gemini en developer router: {e}")
        gemini_client = None
else:
    print("Advertencia: GEMINI_API_KEY no configurada. El análisis de IA no funcionará.")
    gemini_client = None

# =================================================================
# SCHEMAS
# =================================================================
class CaseAnalysisInput(BaseModel):
    """Esquema para la entrada de análisis de un caso clínico."""
    case_description: str

class CaseAnalysisOutput(BaseModel):
    """Esquema para la respuesta después de un análisis exitoso."""
    case_id: int
    analysis_result: str
    user_role: str

# =================================================================
# DEPENDENCIAS DE SEGURIDAD
# =================================================================

def get_admin_for_unlimited_access(db: Session = Depends(get_db)):
    """
    Dependencia que verifica que el usuario autenticado tiene el rol 'admin'.
    Esto garantiza acceso ilimitado y gratuito para el desarrollador.
    """
    current_user = get_current_user(db=db) # Obtiene el usuario del JWT
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Esta ruta es solo para Administradores (Desarrollador)."
        )
    return current_user # Retorna el objeto usuario si es admin

# =================================================================
# 1. RUTA DE ANÁLISIS ILIMITADO (SOLO ADMIN)
# =================================================================
@router.post(
    "/analizar-caso-ilimitado",
    response_model=CaseAnalysisOutput,
    summary="Análisis de Caso Clínico Ilimitado (Exclusivo para Admin)"
)
async def analyze_case_unlimited(
    input_data: CaseAnalysisInput,
    db: Session = Depends(get_db),
    admin_user=Depends(get_admin_for_unlimited_access) # Garantiza que solo el admin acceda
):
    """
    Permite al administrador (desarrollador) enviar un caso clínico y recibir
    el análisis inmediato sin pasar por el flujo de pago.
    """
    if not gemini_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de IA no configurado. Falta GEMINI_API_KEY."
        )

    # 1. Ejecutar el análisis de la IA
    try:
        prompt = (
            "Eres un Analista Clínico de IA avanzado. Analiza el siguiente caso clínico "
            "y proporciona un resumen estructurado con diagnóstico diferencial y posibles "
            "pasos a seguir. No te salgas de tu rol. Caso: " + input_data.case_description
        )
        
        # Uso del cliente correctamente inicializado
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        analysis_result = response.text
    
    except Exception as e:
        print(f"Error en la llamada a la API de Gemini: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener la respuesta de la IA."
        )

    # 2. Crear y guardar el caso en la DB (marcado como pagado/completado)
    new_case = Case(
        user_id=admin_user.id,
        description=input_data.case_description,
        status="completed", # Se marca como completado inmediatamente
        analysis_result=analysis_result,
        payment_intent_id="ADMIN_ACCESS",
        price_amount=0,
        currency="USD",
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow()
    )
    
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 3. Devolver el resultado
    return {
        "case_id": new_case.id,
        "analysis_result": analysis_result,
        "user_role": admin_user.role
    }
