import os
# Importamos la librería y la inicializamos directamente.
# La función 'configure' es más estable que intentar importar Client/types manualmente.
import google.generativeai as genai 
from config import GEMINI_API_KEY, AI_TIMEOUT_SECONDS

# =================================================================
# INICIALIZACIÓN ROBUSTA DE GEMINI
# =================================================================
# Intentamos configurar el cliente inmediatamente usando la clave de entorno.
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        print("INFO: Cliente de Gemini configurado con éxito.")
    else:
        print("ADVERTENCIA: GEMINI_API_KEY no encontrada. El servicio de IA no funcionará.")
except Exception as e:
    print(f"ADVERTENCIA: Fallo en la configuración de Gemini: {e}")

# Creamos una función auxiliar para obtener el cliente, ya configurado.
def get_ai_client():
    # Devolvemos una nueva instancia del cliente por si se necesita, aunque ya esté configurado.
    # Usamos genai.Client() sin argumentos para usar la configuración global.
    try:
        return genai.Client()
    except Exception as e:
        # Esto atrapará errores si la configuración falló
        raise ConnectionError(f"El cliente de Gemini no se pudo obtener. Revise su clave: {e}")


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
        response = client.models.generate_content(
            model=model,
            contents=prompt_parts,
            config={"timeout": AI_TIMEOUT_SECONDS} # Usamos un dict simple para la configuración
        )
        
        return response.text

    except Exception as e:
        raise Exception(f"Fallo en la comunicación con la IA: {str(e)}")

    finally:
        # 3. Limpieza
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
