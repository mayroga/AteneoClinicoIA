from fastapi import APIRouter, HTTPException, Depends, status, Body
from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any
import uuid
import json 
import asyncio # Necesario para compatibilidad asíncrona

# Importaciones para la API de Gemini
from google import genai
from google.genai import types

# Importaciones de módulos locales
from config import settings
from database import (
    insert_case, 
    get_available_cases, 
    get_professional_profile, 
    update_professional_credits, 
    start_active_debate, 
    complete_active_debate, 
    get_ai_report_by_debate_id
)
import professional_service
from auth_routes import AuthResult

# Router para manejar las rutas de casos
router = APIRouter(prefix="/api/v1/cases", tags=["Casos Clínicos y Debate"])

# Inicializar el cliente de Gemini
try:
    gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
except Exception as e:
    print(f"ADVERTENCIA: Gemini Client no pudo inicializarse. Asegúrate de que GEMINI_API_KEY esté configurada. Error: {e}")
    gemini_client = None

# --- Modelos Pydantic ---

class CaseUpload(BaseModel):
    """Modelo para que el Voluntario suba la información del caso."""
    case_details: str = Field(..., min_length=50, description="Descripción detallada del caso clínico.")
    volunteer_email: EmailStr

class RefutationRequest(BaseModel):
    """Modelo para que el Profesional envíe su refutación final."""
    debate_id: int = Field(..., description="ID del debate activo.")
    refutation_text: str = Field(..., min_length=100, description="Texto de la refutación del profesional.")


# --- Dependencia de Roles (Para asegurar acceso) ---

async def is_professional(auth: AuthResult = Depends(lambda e: e)):
    """Dependencia para asegurar que solo los profesionales accedan."""
    if auth.user_type != 'professional':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. Solo para profesionales registrados."
        )
    return auth

async def is_volunteer(auth: AuthResult = Depends(lambda e: e)):
    """Dependencia para asegurar que solo los voluntarios accedan."""
    if auth.user_type != 'volunteer':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido. Solo para voluntarios registrados."
        )
    return auth

# --- Funciones de Integración con Gemini (Ahora asíncronas para no bloquear) ---

async def generate_ai_report(case_details: str) -> Dict[str, Any]:
    """Genera el reporte inicial de la IA que será refutado (Ahora async)."""
    if not gemini_client:
        raise HTTPException(status_code=500, detail="Servicio de IA no disponible.")
    
    # Damos un respiro al bucle de eventos, ya que la librería de Gemini es síncrona.
    # En un entorno de producción, esto debería envolverse en asyncio.to_thread
    await asyncio.sleep(0) 

    system_prompt = (
        "Eres un modelo de IA médica especializado en el diagnóstico y la toma de decisiones clínicas. "
        "Tu tarea es analizar el siguiente caso clínico y generar un 'Reporte de IA' que sirva como "
        "punto de partida para un debate de refutación. Tu reporte debe ser formal, estructurado, y debe "
        "contener un diagnóstico primario (que no siempre es correcto) y una breve justificación. "
        "La respuesta DEBE ser un objeto JSON que contenga las siguientes claves: 'ai_diagnosis', 'ai_justification', y 'ai_questions'. "
        "NO incluyas texto fuera de la estructura JSON."
    )
    
    prompt = f"Caso Clínico para Análisis: {case_details}"
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash-preview-05-20',
            contents=prompt,
            system_instruction=system_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "ai_diagnosis": {"type": "STRING", "description": "Diagnóstico primario de la IA."},
                        "ai_justification": {"type": "STRING", "description": "Justificación concisa del diagnóstico."},
                        "ai_questions": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "3 preguntas críticas para el debate."}
                    },
                    "required": ["ai_diagnosis", "ai_justification", "ai_questions"]
                }
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        print(f"ERROR: Fallo al llamar a Gemini API: {e}")
        raise HTTPException(status_code=500, detail="Fallo en el servicio de generación de reporte de IA.")


async def score_refutation(ai_report: Dict[str, Any], refutation_text: str) -> int:
    """Simula la evaluación de la refutación del profesional por parte de la IA (Ahora async)."""
    if not gemini_client:
        return 0 
    
    # Damos un respiro al bucle de eventos
    await asyncio.sleep(0) 

    scoring_prompt = (
        "Actúas como un juez imparcial y experto en lógica clínica. Tu tarea es evaluar la 'Refutación del Profesional' "
        "contra el 'Reporte Inicial de la IA'. Evalúa la calidad, la evidencia y la coherencia de la refutación. "
        "El sistema de puntuación es de 0 a 100 puntos. Otorga una puntuación alta (90+) si la refutación es muy fuerte. "
        "Tu respuesta DEBE ser un objeto JSON que contenga la clave 'score_points' como un entero (0-100) y 'feedback'."
    )
    
    full_prompt = (
        f"Reporte Inicial de IA:\nDiagnóstico: {ai_report.get('ai_diagnosis')}\nJustificación: {ai_report.get('ai_justification')}\n"
        f"Preguntas Clave: {', '.join(ai_report.get('ai_questions', []))}\n\n"
        f"Refutación del Profesional a Evaluar:\n{refutation_text}"
    )

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash-preview-05-20',
            contents=full_prompt,
            system_instruction=scoring_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "score_points": {"type": "INTEGER", "description": "Puntuación de 0 a 100."},
                        "feedback": {"type": "STRING", "description": "Retroalimentación concisa sobre la refutación."}
                    },
                    "required": ["score_points", "feedback"]
                }
            )
        )
        result = json.loads(response.text)
        return result.get("score_points", 0)
        
    except Exception as e:
        print(f"ERROR: Fallo al calificar la refutación con Gemini: {e}")
        return 0 

# --- ENDPOINTS de Casos (Todos actualizados a async def) ---

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_new_case( # <--- AHORA ASÍNCRONO
    data: CaseUpload, 
    auth: AuthResult = Depends(is_volunteer)
):
    """
    Ruta para que un Voluntario suba un nuevo caso clínico. 
    1. Genera un reporte inicial con Gemini.
    2. Guarda el caso en la base de datos como 'disponible'.
    """
    # 1. Generar Reporte de IA (usando await)
    ai_report = await generate_ai_report(data.case_details)
    
    # 2. Asignar ID único y guardar (usando await)
    new_case_id = str(uuid.uuid4()).split('-')[0] 
    
    success = await insert_case(
        case_id=new_case_id,
        volunteer_email=data.volunteer_email,
        ai_report=ai_report
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fallo al guardar el caso en la base de datos."
        )

    return {
        "message": "Caso subido con éxito y análisis de IA generado.",
        "case_id": new_case_id,
        "ai_report_preview": ai_report
    }

@router.get("/available", response_model=List[Dict[str, Any]])
async def list_available_cases(auth: AuthResult = Depends(is_professional)): # <--- AHORA ASÍNCRONO
    """
    Ruta para que los Profesionales vean la lista de casos disponibles para debatir.
    """
    cases = await get_available_cases() # <--- USANDO AWAIT
    if cases is None:
        raise HTTPException(status_code=500, detail="Fallo al consultar la base de datos.")
    
    return cases


@router.post("/take/{case_id}")
async def take_case_for_debate(case_id: str, auth: AuthResult = Depends(is_professional)): # <--- AHORA ASÍNCRONO
    """
    Ruta para que un Profesional tome un caso disponible.
    1. Verifica créditos. 2. Debita 1 crédito. 3. Marca el caso como 'no disponible'.
    """
    professional_email = auth.email
    
    # 1. Verificar el perfil del profesional (usando await)
    profile = await get_professional_profile(professional_email)
    if not profile or profile.get('credits', 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Créditos insuficientes. Por favor, compre más créditos para tomar un caso."
        )

    # 2. Debitar 1 crédito e iniciar el debate (usando await)
    new_credits = await update_professional_credits(professional_email, -1) # Debitar 1
    
    if new_credits is None:
        raise HTTPException(status_code=500, detail="Error al debitar créditos.")

    debate_id = await start_active_debate(case_id, professional_email) # <--- USANDO AWAIT

    if debate_id is None:
        # Revertir el crédito si el debate no pudo iniciar (usando await)
        await update_professional_credits(professional_email, 1)  
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="El caso ya fue tomado o no está disponible."
        )

    return {
        "message": f"Caso {case_id} tomado con éxito. Debate ID: {debate_id}.",
        "remaining_credits": new_credits,
        "debate_id": debate_id
    }


@router.post("/refute")
async def submit_refutation(data: RefutationRequest, auth: AuthResult = Depends(is_professional)): # <--- AHORA ASÍNCRONO
    """
    Ruta para que el Profesional envíe su refutación final.
    1. Obtiene el reporte de IA original.
    2. Evalúa la refutación con la IA.
    3. Si pasa el umbral, actualiza el ranking (usando el servicio).
    4. Cierra el debate.
    """
    # 1. Obtener el reporte de IA real (usando await)
    ai_report = await get_ai_report_by_debate_id(data.debate_id)
    
    if not ai_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El debate activo o el reporte de IA asociado no fue encontrado."
        )

    # 2. Puntuación de la refutación por la IA (usando await)
    score = await score_refutation(ai_report, data.refutation_text)
    
    message = "Refutación enviada. Recibirás tu puntuación y retroalimentación pronto."
    
    # 3. Actualizar Ranking si la puntuación es alta (usando el servicio)
    if score >= 80:
        # Asumimos que esta función es síncrona o maneja su propia async
        professional_service.update_refutation_ranking(auth.email, 1) 
        message = f"¡Felicidades! Tu refutación (Puntuación: {score}) ha sido exitosa y has ganado 1 punto de ranking."
    else:
        message = f"Refutación completada (Puntuación: {score}). No alcanzó el umbral para ganar ranking esta vez."
    
    # 4. Marcar el debate como completado (usando await)
    success_close = await complete_active_debate(data.debate_id)
    
    if not success_close:
        print(f"ERROR: No se pudo cerrar el debate {data.debate_id} al finalizar.")
        message += " (Error interno al cerrar el debate)."
        
    return {
        "message": message,
        "final_score": score,
    }
