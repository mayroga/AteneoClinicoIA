from pydantic import BaseModel, Field
from typing import Optional, List

# --- Inputs del Usuario ---

class WaiverAcceptance(BaseModel):
    email: str
    user_type: str = Field(description="Debe ser 'profesional' o 'voluntario'")

class ProfessionalRegister(BaseModel):
    email: str
    name: str
    specialty: str

class CreatePaymentIntent(BaseModel):
    amount: int = Field(description="Monto en céntimos (ej: 4000 para $40.00).")
    currency: str = Field(default="usd")
    user_email: str
    product_type: str = Field(description="Voluntario_Caso | Profesional_Creditos")

# --- Output de la IA (Tesis Clínica) ---

class VisualReference(BaseModel):
    reporte_textual: str = Field(description="Reporte textual generado por Gemini del análisis visual.")
    search_term: str = Field(description="Término para búsqueda externa de código abierto.")

class TesisClinica(BaseModel):
    case_id: str
    especialidad: str
    nivel_complejidad: str
    diagnostico_propuesto: str
    plan_tratamiento: str
    laboratorios_simulados: dict
    referencia_visual: VisualReference
    puntos_clave_debate: List[str]
