import os
import google.genai as genai 
from config import GEMINI_API_KEY, AI_TIMEOUT_SECONDS

# =================================================================
# INICIALIZACIÓN ROBUSTA DE GEMINI (ACTUALIZADA)
# =================================================================
# Se elimina el bloque try/except con genai.configure().
# La configuración ahora se hace directamente al crear el cliente.

if not GEMINI_API_KEY:
    print("ADVERTENCIA: GEMINI_API_KEY no encontrada. El servicio de IA no funcionará.")

def get_ai_client():
    """
    Crea y devuelve una instancia del cliente de Gemini, inyectando la clave de API.
    Este es el método robusto para el nuevo SDK (google-genai).
    """
    if not GEMINI_API_KEY:
        raise ConnectionError("GEMINI_API_KEY no está configurada. No se puede iniciar el cliente de Gemini.")
        
    try:
        # Se pasa la clave de API directamente al constructor del cliente.
        # Esto reemplaza la necesidad de la configuración global (genai.configure).
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        # Esto atrapará errores si la inicialización del cliente falla por otras razones
        raise ConnectionError(f"El cliente de Gemini no se pudo inicializar. Revise la clave de API y dependencias: {e}")

# =================================================================
# FUNCIÓN DE ANÁLISIS
# =================================================================

def analyze_case(description: str, file_path: str = None) -> str:
    """
    Ejecuta el análisis multimodal de un caso clínico usando Gemini.
    """
    client = get_ai_client()
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
            file_part = client.files.upload(file=file_path)
            prompt_parts.append(file_part)
        
        # 2. Llamar al modelo de IA
        # Se usa 'request_options' para pasar el timeout, ya que 'config' está obsoleto.
        response = client.models.generate_content(
            model=model,
            contents=prompt_parts,
            request_options={"timeout": AI_TIMEOUT_SECONDS}  
        )
        
        return response.text

    except Exception as e:
        raise Exception(f"Fallo en la comunicación con la IA: {str(e)}")

    finally:
        # 3. Limpieza
        if file_part:
            try:
                # El cliente.files.delete requiere el objeto File original o su 'name'
                client.files.delete(name=file_part.name)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo de Gemini: {e}")
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo local: {e}")
