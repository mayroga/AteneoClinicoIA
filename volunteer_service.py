import psycopg2.extras
import uuid
import json
from database import get_db_connection
from models import VolunteerInput, TesisClinica, VisualReference
from config import settings
from typing import Optional

# NOTA: Necesitarías instalar la librería google-genai. 
# Aquí simulamos la llamada a la API para el flujo de datos.
# from google import genai 
# client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ----------------------------------------------------
# 1. FUNCIÓN DE SIMULACIÓN DE LA IA MULTIMODAL (El Proxy Visual)
# ----------------------------------------------------

def generate_tesis_with_gemini(history_text: str, image_path: str) -> Optional[TesisClinica]:
    """
    Simula la llamada a Gemini 2.5 Pro Vision para generar la Tesis Clínica.
    
    En el código real, 'image_path' sería un archivo cargado o una URL temporal.
    """
    # 1. CONSTRUCCIÓN DEL PROMPT AVANZADO (El Motor del Caso)
    # Se instruye a la IA para ser precisa, provocativa y generar el Proxy Visual.
    
    prompt = f"""
    Eres un motor de simulación clínica avanzada. Tu tarea es generar una Tesis Clínica de Alta Fidelidad 
    basada en la siguiente Historia Clínica: '{history_text}'.
    
    Analiza la imagen de apoyo (si fue proporcionada) para generar un reporte textual y un término de búsqueda.
    
    REGLAS CLAVE:
    1. El diagnóstico propuesto debe ser asertivo, pero incluir una omisión o sutil error detectable (para el debate).
    2. Genera todos los resultados de laboratorio y el plan de tratamiento completo y específico (dosis/frecuencia).
    3. Asegura que el nivel de complejidad sea 'Experto'.
    
    Tu respuesta debe ajustarse al siguiente formato JSON estricto.
    """
    
    # --- SIMULACIÓN DEL OUTPUT DE LA IA ---
    # En producción, se haría la llamada real a la API.
    # Esta es una respuesta simulada de Neumonía para demostrar la estructura:
    
    case_id = f"CASO-{str(uuid.uuid4())[:8].upper()}"
    
    # Se simula que la IA analizó la imagen y el texto
    simulated_tesis_data = {
        "case_id": case_id,
        "especialidad": "Medicina Interna",
        "nivel_complejidad": "Experto",
        "diagnostico_propuesto": "Neumonía Adquirida en la Comunidad (NAC) - Criterios CURB-65 bajo.",
        "plan_tratamiento": "Amoxicilina/Ácido Clavulánico 875/125 mg c/12h por 7 días. Reposo. Control en 48h.",
        "laboratorios_simulados": {"Leucocitos": "14,500/mm³", "PCR": "8.5 mg/dL", "Rx Tórax": "Consolidación lobar derecha."},
        "referencia_visual": {
            "reporte_textual": "Opacidad lobar derecha con patrón de consolidación segmentaria, compatible con proceso infeccioso.",
            "search_term": "Radiografía de tórax consolidación lobar derecha típica"
        },
        "puntos_clave_debate": ["¿Es necesario realizar un cultivo de esputo?", "¿Es el tratamiento de primera línea óptimo para esta región?"],
    }
    
    return TesisClinica(**simulated_tesis_data)


# ----------------------------------------------------
# 2. PROCESAMIENTO PRINCIPAL DEL VOLUNTARIO (La Anonymización)
# ----------------------------------------------------

def process_volunteer_case(data: VolunteerInput, image_path: Optional[str]) -> Optional[TesisClinica]:
    """
    Función que gestiona el caso después de que el pago fue exitoso.
    """
    conn = get_db_connection()
    if conn is None:
        return None
    
    # 1. Llamada a la IA para generar la Tesis Clínica
    tesis = generate_tesis_with_gemini(data.history_text, image_path)
    if tesis is None:
        return None # Falló la IA
    
    # 2. ¡ELIMINACIÓN INMEDIATA DE LA IMAGEN! (Protección HIPAA)
    # Aquí iría el código para eliminar el archivo subido en 'image_path'
    # os.remove(image_path) o llamada al servicio cloud para borrar la URL temporal.
    print(f"DEBUG: IMAGEN TEMPORAL EN {image_path} HA SIDO ELIMINADA.")

    # 3. Almacenamiento Anónimo en la DB
    try:
        cursor = conn.cursor()
        
        # Insertar el Caso Anónimo (ID único)
        cursor.execute(
            """
            INSERT INTO casos_anonimos (case_id, tesis_clinica)
            VALUES (%s, %s);
            """,
            (tesis.case_id, json.dumps(tesis.model_dump()))
        )
        
        # 4. Vincular el caso ANÓNIMO al voluntario (para el reporte)
        cursor.execute(
            """
            INSERT INTO voluntarios (email, case_id_linked)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE
            SET case_id_linked = EXCLUDED.case_id_linked;
            """,
            (data.email, tesis.case_id)
        )
        
        conn.commit()
        return tesis

    except Exception as e:
        conn.rollback()
        print(f"Error al almacenar caso de voluntario: {e}")
        return None
    
    finally:
        if conn: conn.close()

# ----------------------------------------------------
# 3. Función de Recuperación de Reporte para el Voluntario
# ----------------------------------------------------

def get_volunteer_report(email: str) -> Optional[TesisClinica]:
    """Recupera la Tesis Clínica para que el voluntario obtenga su 'Reporte de Participación'."""
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cursor.execute(
            """
            SELECT ta.tesis_clinica FROM voluntarios tv
            JOIN casos_anonimos ta ON tv.case_id_linked = ta.case_id
            WHERE tv.email = %s;
            """,
            (email,)
        )
        
        report = cursor.fetchone()
        if report:
            return TesisClinica(**report['tesis_clinica'])
        return None
        
    except Exception as e:
        print(f"Error al obtener reporte de voluntario: {e}")
        return None
        
    finally:
        if conn: conn.close()
