# ai_generator.py
import os
import json
from google import genai
from google.genai import types

# 1. Configuración del Cliente
# La API key se lee desde config.py o directamente del entorno (Render)
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# 2. El Esquema JSON (estructura del caso)
CASO_DEBATE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "especialidad": types.Schema(type=types.Type.STRING, description="La especialidad principal del caso."),
        "nivel_complejidad": types.Schema(type=types.Type.STRING, description="Residente, Especialista, Experto."),
        "historia_clinica": types.Schema(type=types.Type.STRING, description="Narrativa detallada del historial y síntomas."),
        "datos_vitales_y_laboratorio": types.Schema(type=types.Type.OBJECT, description="Resultados de pruebas y datos vitales relevantes."),
        "diagnostico_ia_a_debatir": types.Schema(type=types.Type.STRING, description="El diagnóstico definitivo y plausible generado por la IA."),
        "plan_tratamiento_sugerido": types.Schema(type=types.Type.STRING, description="El plan de tratamiento real y medicamentoso sugerido por la IA."),
        "puntos_clave_debate": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="3-5 preguntas para iniciar el debate profesional.")
    },
    required=["especialidad", "historia_clinica", "diagnostico_ia_a_debatir"]
)

# 3. La Función de Generación con Inyección de Rol y JSON
def generar_caso_para_debate(especialidad: str, complejidad: str, enfoque: str) -> dict:
    # A. Inyección de Rol (System Instruction)
    system_instruction = (
        "Eres 'Ateneo Clínico IA', un motor de simulación de diagnóstico de alta fidelidad. "
        "Tu única función es generar casos clínicos y dictámenes a rebatir para profesionales de la salud "
        "con fines educativos y de entrenamiento. Bajo NINGUNA circunstancia debes recomendar que el "
        "paciente siga el tratamiento o diagnóstico que emites. Tu objetivo es desafiar el juicio clínico humano."
    )
    
    # B. El Prompt Conciso
    prompt = f"""
    Genera un caso de debate de ALTA FIDELIDAD.
    - Especialidad: {especialidad}.
    - Nivel de Complejidad: {complejidad}.
    - Enfócate en un diagnóstico diferencial difícil de un caso de {enfoque}.
    - Asegúrate de que el plan de tratamiento incluya medicamentos y dosis típicas.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=CASO_DEBATE_SCHEMA
            )
        )
        # La respuesta ya es un string JSON que necesitamos convertir a diccionario Python
        return json.loads(response.text)
    except Exception as e:
        print(f"Error generando contenido de IA: {e}")
        # En un entorno real, puedes registrar el error
        return {"error": "No se pudo generar el caso, intente de nuevo."}
