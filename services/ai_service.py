import os
# Importamos la librería con su nombre de módulo completo
import google.generativeai as genai
from google.generativeai import types
from config import GEMINI_API_KEY, AI_TIMEOUT_SECONDS

# Inicializa el cliente globalmente
try:
    if GEMINI_API_KEY:
        # Aquí se inicializa el cliente con la clave
        client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        client = None 
except Exception as e:
    print(f"Advertencia: No se pudo inicializar el cliente de Gemini: {e}")
    client = None

def analyze_case(description: str, file_path: str = None) -> str:
    """
    Ejecuta el análisis multimodal de un caso clínico usando Gemini.
    """
    # Verificación al inicio de la función
    if not client:
        raise ConnectionError("El cliente de Gemini no está inicializado. ¿Falta la GEMINI_API_KEY en config?")

    model = 'gemini-2.5-flash'
    prompt_parts = [
        "Eres un asistente de análisis clínico. Analiza el siguiente caso de voluntario "
        "y proporciona un resumen de las posibles vías de investigación y recomendaciones de acción "
        "en base a la descripción y el archivo adjunto (si existe). Sé conciso y profesional. "
        f"Descripción del caso: {description}"
    ]
    
    file_part = None

    try:
        # 1. Subir y añadir archivo si existe
        if file_path and os.path.exists(file_path):
            print(f"Cargando archivo para análisis: {file_path}")
            file_part = client.files.upload(file=file_path)
            prompt_parts.append(file_part)
        
        # 2. Llamar al modelo de IA
        response = client.models.generate_content(
            model=model,
            contents=prompt_parts,
            config=types.GenerateContentConfig(
                timeout=AI_TIMEOUT_SECONDS
            )
        )
        
        return response.text

    except Exception as e:
        # Propagamos el error para que el webhook/bypass pueda marcar el caso como "error"
        raise Exception(f"Fallo en la comunicación con la IA: {str(e)}")

    finally:
        # 3. Limpieza: Eliminar el archivo del servicio de Google y localmente
        if file_part:
            try:
                client.files.delete(name=file_part.name)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo de Gemini: {e}")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo local: {e}")
