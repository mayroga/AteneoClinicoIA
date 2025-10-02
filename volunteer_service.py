from google import genai
from google.genai import types
import json
import os
import psycopg2.extras
from typing import Optional, Dict, Any
from uuid import uuid4

from config import settings
from database import get_db_connection
from models import TesisClinica

# Inicialización del cliente Gemini
gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
model_name = "gemini-2.5-flash" 

# ----------------------------------------------------
# LÓGICA DE PROCESAMIENTO DEL CASO (GEMINI VISION)
# ----------------------------------------------------

def generate_ai_report(history_text: str, image_path: str) -> Optional[TesisClinica]:
    """
    Usa Gemini Vision para analizar el caso y generar una Tesis Clínica estructurada.
    """
    
    # 1. Cargar la imagen
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
            image_part = types.Part.from_bytes(data=image_data, mime_type="image/jpeg")
    except FileNotFoundError:
        print("ERROR: Archivo de imagen no encontrado.")
        return None

    # 2. Definir el esquema JSON de salida (Crucial para la fiabilidad)
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "case_id": {"type": "string"},
            "patient_age": {"type": "integer"},
            "patient_gender": {"type": "string"},
            "chief_complaint": {"type": "string"},
            "history_summary": {"type": "string"},
            "ai_hypothesis": {"type": "string"},
            "differential_diagnoses": {"type": "array", "items": {"type": "string"}},
            "diagnostic_plan": {"type": "string"}
        },
        "required": ["case_id", "chief_complaint", "history_summary", "ai_hypothesis", "differential_diagnoses", "diagnostic_plan"]
    }

    # 3. Prompt de la IA
    system_prompt = (
        "Eres un experto en simulación clínica y un sistema de anonimización. "
        "Tu tarea es generar una 'Tesis Clínica' basada en una Historia Clínica e imagen de apoyo. "
        "Asegura la anonimización. Genera la respuesta estrictamente en formato JSON de acuerdo al esquema."
    )
    user_prompt = (
        f"Analiza la Historia Clínica provista y la imagen anexa. Genera una Tesis Clínica completa y estructurada. "
        f"Historia Clínica: {history_text}"
    )

    try:
        response = gemini_client.models.generate_content(
            model=model_name,
            contents=[user_prompt, image_part],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=response_schema
            ),
        )
        
        # 4. Parsear y validar la salida
        json_str = response.candidates[0].content.parts[0].text.strip()
        data = json.loads(json_str)
        data['case_id'] = str(uuid4()) # Aseguramos un ID único

        return TesisClinica(**data)
    
    except Exception as e:
        print(f"ERROR de Gemini en la generación de Tesis: {e}")
        return None

# ----------------------------------------------------
# LÓGICA DE BASE DE DATOS
# ----------------------------------------------------

def process_volunteer_case(email: str, history_text: str, image_path: str) -> Optional[TesisClinica]:
    """
    Genera el reporte de IA y lo guarda en la DB.
    """
    conn = get_db_connection()
    if conn is None: return None

    # Llamada a la IA
    ai_report = generate_ai_report(history_text, image_path)
    if not ai_report:
        conn.close()
        return None
        
    try:
        cursor = conn.cursor()
        
        # 1. Serializar el reporte de la IA a JSON para PostgreSQL
        report_json = ai_report.model_dump_json()

        # 2. Insertar el caso en la tabla 'cases'
        cursor.execute(
            "INSERT INTO cases (case_id, volunteer_email, ai_report) VALUES (%s, %s, %s);",
            (ai_report.case_id, email, report_json)
        )
        conn.commit()
        return ai_report
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al guardar el caso: {e}")
        return None
    finally:
        if conn: conn.close()

def get_volunteer_report_and_viral_message(email: str) -> Optional[Dict[str, Any]]:
    """
    Recupera la Tesis Clínica y prepara el mensaje viral.
    """
    conn = get_db_connection()
    if conn is None: return None

    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Busca el último caso de este voluntario
        cursor.execute(
            "SELECT case_id, ai_report FROM cases WHERE volunteer_email = %s ORDER BY creation_timestamp DESC LIMIT 1;",
            (email,)
        )
        case = cursor.fetchone()
        
        if case:
            case_id = case['case_id']
            report_data = case['ai_report'] # Es un dict/json
            
            # Mensaje viral listo para copiar y pegar (Marketing viral orgánico)
            viral_message = (
                f"¡Desafío a la comunidad médica! Acabo de someter mi caso a la IA de Ateneo Clínico ({case_id}) "
                f"para que miles de profesionales debatan el diagnóstico. "
                f"La IA sugiere: '{report_data.get('ai_hypothesis', 'Diagnóstico no disponible')}'. "
                f"¿Tienen un mejor diagnóstico? #AteneoIA #ClinicalDebate"
            )
            
            return {'report': report_data, 'viral_message': viral_message}
        return None
        
    except Exception as e:
        print(f"ERROR DB al recuperar reporte: {e}")
        return None
    finally:
        if conn: conn.close()
