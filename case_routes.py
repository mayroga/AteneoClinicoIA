from fastapi import APIRouter, HTTPException, Depends, status, Body
from pydantic import BaseModel, EmailStr, Field
from typing import List, Dict, Any
import uuid
import json # <-- ¡CORRECCIÓN APLICADA AQUÍ! Se requiere para json.loads()

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
    update_refutation_score,
    complete_active_debate
)
from auth_routes import AuthResult # Usamos la clase de resultado de autenticación

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

# --- Funciones de Integración con Gemini ---

def generate_ai_report(case_details: str) -> Dict[str, Any]:
    """Genera el reporte inicial de la IA que será refutado."""
    if not gemini_client:
        raise HTTPException(status_code=500, detail="Servicio de IA no disponible.")
    
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
            system_instruction={
                "parts": [{"text": system_prompt}]
            },
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
        # El texto de la respuesta JSON es un string, lo parseamos
        return json.loads(response.text)
        
    except Exception as e:
        print(f"ERROR: Fallo al llamar a Gemini API: {e}")
        raise HTTPException(status_code=500, detail="Fallo en el servicio de generación de reporte de IA.")


def score_refutation(ai_report: Dict[str, Any], refutation_text: str) -> int:
    """Simula la evaluación de la refutación del profesional por parte de la IA."""
    if not gemini_client:
        return 0 # Retorno 0 si el servicio no está disponible

    # Creamos un prompt para que Gemini actúe como evaluador imparcial
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
            system_instruction={"parts": [{"text": scoring_prompt}]},
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
        # Devolvemos solo los puntos de la puntuación
        result = json.loads(response.text)
        return result.get("score_points", 0)
        
    except Exception as e:
        print(f"ERROR: Fallo al calificar la refutación con Gemini: {e}")
        return 0 # Fallo en la puntuación

# --- ENDPOINTS de Casos ---

@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_new_case(
    data: CaseUpload, 
    auth: AuthResult = Depends(is_volunteer)
):
    """
    Ruta para que un Voluntario suba un nuevo caso clínico. 
    1. Genera un reporte inicial con Gemini.
    2. Guarda el caso en la base de datos como 'disponible'.
    """
    # 1. Generar Reporte de IA
    ai_report = generate_ai_report(data.case_details)
    
    # 2. Asignar ID único y guardar
    new_case_id = str(uuid.uuid4()).split('-')[0] # ID corto para URL/fácil lectura
    
    success = insert_case(
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
def list_available_cases(auth: AuthResult = Depends(is_professional)):
    """
    Ruta para que los Profesionales vean la lista de casos disponibles para debatir.
    """
    cases = get_available_cases()
    if cases is None:
        raise HTTPException(status_code=500, detail="Fallo al consultar la base de datos.")
    
    # Ocultar o simplificar la información sensible antes de enviar (no necesario con el JSON de la DB)
    return cases


@router.post("/take/{case_id}")
def take_case_for_debate(case_id: str, auth: AuthResult = Depends(is_professional)):
    """
    Ruta para que un Profesional tome un caso disponible.
    1. Verifica créditos. 2. Debita 1 crédito. 3. Marca el caso como 'no disponible'.
    """
    professional_email = auth.email
    
    # 1. Verificar el perfil del profesional
    profile = get_professional_profile(professional_email)
    if not profile or profile.get('credits', 0) <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Créditos insuficientes. Por favor, compre más créditos para tomar un caso."
        )

    # 2. Debitar 1 crédito e iniciar el debate
    new_credits = update_professional_credits(professional_email, -1) # Debitar 1
    
    if new_credits is None:
        raise HTTPException(status_code=500, detail="Error al debitar créditos.")

    debate_id = start_active_debate(case_id, professional_email)

    if debate_id is None:
        # Revertir el crédito si el debate no pudo iniciar (ej: caso ya tomado)
        update_professional_credits(professional_email, 1) 
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
def submit_refutation(data: RefutationRequest, auth: AuthResult = Depends(is_professional)):
    """
    Ruta para que el Profesional envíe su refutación final.
    1. Evalúa la refutación con la IA.
    2. Si pasa el umbral, actualiza el ranking.
    3. Cierra el debate.
    """
    # Nota: Aquí deberíamos obtener el ai_report original del caso para la puntuación. 
    # Por simplicidad, asumiremos que el profesional tiene acceso a él y se pasa implícitamente.
    # En una versión más compleja, obtendríamos el case_id desde el debate_id y luego el ai_report.
    
    # SIMULACIÓN DE OBTENCIÓN DE REPORTE AI:
    # Para que el código sea ejecutable, asumimos un mock de reporte.
    # *En producción, este paso requeriría una consulta a la DB.*
    mock_ai_report = {
        "ai_diagnosis": "Neumonía Atípica por Mycoplasma.",
        "ai_justification": "Fiebre baja, tos seca y síntomas extrapulmonares indican Mycoplasma.",
        "ai_questions": ["¿Se realizó serología?", "¿Hay leucocitosis?", "¿Responde a Macrólidos?"]
    }

    # 1. Puntuación de la refutación por la IA
    score = score_refutation(mock_ai_report, data.refutation_text)
    
    message = "Refutación enviada. Recibirás tu puntuación y retroalimentación pronto."
    
    # 2. Actualizar Ranking si la puntuación es alta (Ej: Umbral de éxito = 80 puntos)
    if score >= 80:
        update_refutation_score(auth.email, 1) # Añadir 1 punto al ranking por refutación exitosa
        message = f"¡Felicidades! Tu refutación (Puntuación: {score}) ha sido exitosa y has ganado 1 punto de ranking."
    else:
        message = f"Refutación completada (Puntuación: {score}). No alcanzó el umbral para ganar ranking esta vez."
    
    # 3. Marcar el debate como completado
    success_close = complete_active_debate(data.debate_id)
    
    if not success_close:
        print(f"ERROR: No se pudo cerrar el debate {data.debate_id} al finalizar.")
        message += " (Error interno al cerrar el debate)."
        
    return {
        "message": message,
        "final_score": score,
    }
