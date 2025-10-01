import psycopg2.extras
import uuid
import json
import os
from database import get_db_connection # Importación corregida
from models import TesisClinica, VisualReference # Importación corregida
from config import settings # Importación corregida
from typing import Optional

# NOTA: Necesitarías la librería 'google-genai' aquí
# from google import genai 
# client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ----------------------------------------------------
# 1. FUNCIÓN PRINCIPAL DE LA IA (Simulación del Proxy Visual)
# ----------------------------------------------------

def generate_tesis_with_gemini(history_text: str, image_path: str) -> Optional[TesisClinica]:
    """
    Simula la llamada a Gemini 2.5 Pro Vision. Esto es el PROXY VISUAL.
    
    En el código real, se cargaría la imagen desde 'image_path' y se enviaría a la API.
    """
    # ... (El código de generación de prompt y llamada a Gemini iría aquí) ...
    
    # --- SIMULACIÓN DEL OUTPUT DE LA IA (Neumonía, como ejemplo) ---
    case_id = f"CASO-{str(uuid.uuid4())[:8].upper()}"
    
    simulated_tesis_data = {
        "case_id": case_id,
        "especialidad": "Medicina Interna",
        "nivel_complejidad": "Experto",
        "diagnostico_propuesto": "Neumonía Adquirida en la Comunidad (NAC) - Sospecha de Mycoplasma.",
        "plan_tratamiento": "Azitromicina 500 mg dosis única, luego 250 mg diarios por 4 días más.",
        "laboratorios_simulados": {"Leucocitos": "9,200/mm³", "Rx Tórax": "Infiltrado intersticial en base pulmonar izquierda."},
        "referencia_visual": {
            "reporte_textual": "Infiltrado de patrón intersticial sutil en base pulmonar izquierda, sin derrame.",
            "search_term": "Radiografía de tórax infiltrado intersticial atípico"
        },
        "puntos_clave_debate": ["¿Es el Azitromicina el tratamiento de primera elección empírico?", "¿Se requiere hospitalización?"],
    }
    
    return TesisClinica(**simulated_tesis_data)


# ----------------------------------------------------
# 2. PROCESAMIENTO PRINCIPAL DEL VOLUNTARIO (Anonimización)
# ----------------------------------------------------

def process_volunteer_case(email: str, history_text: str, image_path: Optional[str]) -> Optional[TesisClinica]:
    """
    Función que gestiona el caso después del pago y Waiver.
    """
    conn = get_db_connection()
    if conn is None: return None
    
    # 1. Llamada a la IA para generar la Tesis Clínica
    tesis = generate_tesis_with_gemini(history_text, image_path)
    if tesis is None: return None
    
    # 2. ¡ELIMINACIÓN INMEDIATA DE LA IMAGEN! (Doble Protección HIPAA)
    if image_path and os.path.exists(image_path):
        os.remove(image_path)
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
            (email, tesis.case_id)
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
# 3. Función de Recuperación de Reporte
# ----------------------------------------------------

def get_volunteer_report(email: str) -> Optional[TesisClinica]:
    """Recupera la Tesis Clínica para el 'Reporte de Participación' del voluntario."""
    conn = get_db_connection()
    if conn is None: return None
    
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
            # Asegura que el JSON se convierta en el modelo Pydantic
            return TesisClinica(**report['tesis_clinica'])
        return None
        
    except Exception as e:
        print(f"Error al obtener reporte de voluntario: {e}")
        return None
        
    finally:
        if conn: conn.close()
