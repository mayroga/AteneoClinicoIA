import requests
from config import GEMINI_API_KEY

GEMINI_API_URL = "https://api.gemini.com/v1/clinical"

def generate_diagnosis(case_text: str, case_media: str = None):
    """
    Envía un caso clínico a la IA Gemini y obtiene un diagnóstico educativo.
    case_text: descripción del caso clínico
    case_media: URL de imagen o video (opcional)
    """
    payload = {
        "api_key": GEMINI_API_KEY,
        "text": case_text,
        "media_url": case_media
    }
    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        diagnosis = data.get("diagnosis", "No se pudo generar diagnóstico")
        return diagnosis
    except requests.RequestException as e:
        print(f"Error al conectar con Gemini: {str(e)}")
        return "Error en la IA. Intenta más tarde."

# Funciones adicionales para casos específicos
def analyze_case_for_learning(case_text: str, case_media: str = None):
    """
    Devuelve un análisis educativo del caso, útil para voluntarios.
    """
    diagnosis = generate_diagnosis(case_text, case_media)
    analysis = f"""
    <p>Diagnóstico educativo generado por IA:</p>
    <p>{diagnosis}</p>
    <p>Recuerda: este resultado es solo con fines educativos y no sustituye la consulta médica profesional.</p>
    """
    return analysis
