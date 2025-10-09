import os
import requests
from config import GEMINI_API_KEY

GEMINI_ENDPOINT = "https://api.gemini.com/v1/analyze"  # Ajusta según documentación real

# -----------------------------
# Analizar caso clínico
# -----------------------------
def analyze_case(case_data: dict):
    """
    Envía datos de un caso clínico a Gemini API para análisis.
    case_data: {
        "type": "text" | "image" | "video",
        "content": "texto base64 o URL de archivo"
    }
    """
    headers = {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "case_type": case_data.get("type"),
        "case_content": case_data.get("content")
    }
    
    try:
        response = requests.post(GEMINI_ENDPOINT, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()  # Devuelve resultado del análisis de IA
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}

# -----------------------------
# Generar resumen educativo y terapéutico
# -----------------------------
def generate_case_summary(case_analysis: dict):
    """
    Toma el resultado de Gemini y genera un resumen educativo y terapéutico.
    """
    try:
        # Ejemplo básico: puedes personalizar según la respuesta de Gemini
        summary = {
            "diagnosis_suggestions": case_analysis.get("diagnoses", []),
            "recommendations": case_analysis.get("recommendations", []),
            "confidence": case_analysis.get("confidence_score", 0)
        }
        return summary
    except Exception as e:
        return {"error": str(e)}

# -----------------------------
# Detectar idioma y adaptar análisis
# -----------------------------
def detect_language_and_analyze(case_text: str):
    """
    Detecta idioma y envía el caso a Gemini adaptando idioma.
    """
    try:
        # Método simple de detección (puedes mejorar con librerías externas)
        if any(ord(c) > 127 for c in case_text):
            language = "es"  # Español
        else:
            language = "en"  # Inglés
        
        case_data = {
            "type": "text",
            "content": case_text,
            "language": language
        }
        return analyze_case(case_data)
    except Exception as e:
        return {"error": str(e)}
