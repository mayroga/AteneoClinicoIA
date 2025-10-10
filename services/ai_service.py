# Archivo a identificar: services/ai_service.py

import os
from config import GEMINI_API_KEY, AI_TIMEOUT_SECONDS
# =================================================================
# CORRECCIÓN CRÍTICA DE IMPORTACIÓN: Usamos el nombre del paquete
# =================================================================
import google.generativeai as genai
from google.generativeai import types
# =================================================================

# Inicializa el cliente globalmente (buena práctica si se usa en varios lugares)
try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        # Esto lanzará un error si se llama analyze_case sin la clave
        client = None 
except Exception as e:
    print(f"Advertencia: No se pudo inicializar el cliente de Gemini: {e}")
    client = None

def analyze_case(description: str, file_path: str = None) -> str:
    """
    Ejecuta el análisis multimodal de un caso clínico usando Gemini.
    """
    if not client:
        raise ConnectionError("El cliente de Gemini no está inicializado. ¿Falta la GEMINI_API_KEY?")

    model = 'gemini-2.5-flash'
    
    prompt_parts = [
        "Eres un asistente de análisis clínico. Analiza el siguiente caso de voluntario "
        "y proporciona un resumen de las posibles vías de investigación y recomendaciones de acción "
        "en base a la descripción y el archivo adjunto (si existe). Sé conciso y profesional. "
        f"Descripción del caso: {description}"
    ]
    
    file_part = None

    try:
        # Añadir el archivo si existe
        if file_path and os.path.exists(file_path):
            print(f"Cargando archivo para análisis: {file_path}")
            # Subir el archivo al servicio de Google
            file_part = client.files.upload(file=file_path)
            prompt_parts.append(file_part)
        
        # Llama al modelo de IA
        response = client.models.generate_content(
            model=model,
            contents=prompt_parts,
            config=types.GenerateContentConfig(
                # Usa el timeout definido en config.py (ej. 60s)
                timeout=AI_TIMEOUT_SECONDS
            )
        )
        
        return response.text

    except Exception as e:
        # Manejo de errores específicos de la API (timeout, etc.)
        raise Exception(f"Fallo en la comunicación con la IA: {str(e)}")

    finally:
        # Eliminar el archivo del servicio de Google y localmente (limpieza)
        if file_part:
            try:
                client.files.delete(name=file_part.name)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo de Gemini: {e}")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
