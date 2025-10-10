from config import GEMINI_API_KEY
from google import genai
from google.genai import types

# CRÍTICO: La librería de Gemini debe estar instalada (pip install google-genai)

def analyze_case(description: str, file_path: str = None) -> str:
    """
    Ejecuta el análisis multimodal de un caso clínico usando Gemini.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no está configurada. El servicio de IA no puede iniciar.")
        
    try:
        # Inicializa el cliente de la API
        client = genai.Client(api_key=GEMINI_API_KEY)
        model = 'gemini-2.5-flash'
        
        prompt_parts = [
            "Eres un asistente de análisis clínico. Analiza el siguiente caso de voluntario "
            "y proporciona un resumen de las posibles vías de investigación y recomendaciones de acción "
            "en base a la descripción y el archivo adjunto (si existe). Sé conciso y profesional. "
            f"Descripción del caso: {description}"
        ]
        
        # Añadir el archivo si existe
        if file_path and os.path.exists(file_path):
            print(f"Cargando archivo para análisis: {file_path}")
            # El archivo debe ser cargado correctamente antes de enviarlo
            file_part = client.files.upload(file=file_path)
            prompt_parts.append(file_part)
        
        # Llama al modelo de IA
        response = client.models.generate_content(
            model=model,
            contents=prompt_parts,
            config=types.GenerateContentConfig(
                # Aumenta el timeout si el análisis es largo
                timeout=60 # 60 segundos para evitar que la llamada falle
            )
        )
        
        # Eliminar el archivo temporal después del análisis
        if 'file_part' in locals():
            client.files.delete(name=file_part.name)
            os.remove(file_path) # Eliminar también el archivo local anonimizado

        return response.text

    except Exception as e:
        print(f"FATAL ERROR en analyze_case: {str(e)}")
        # Propaga el error para que el webhook marque el caso como "error"
        raise Exception(f"Fallo en la comunicación con la IA: {str(e)}")
