from pydantic import BaseModel, Field
from typing import Optional, List

# --- Seguridad y Legalidad ---
class WaiverAcceptance(BaseModel):
    """Esquema para registrar la aceptación legal de términos."""
    email: str = Field(..., description="Email único del usuario.")
    user_type: str = Field(..., description="Tipo de usuario: 'volunteer' o 'professional'.")

# --- Monetización (Stripe) ---
class CreatePaymentIntent(BaseModel):
    """Esquema para crear una intención de pago en Stripe."""
    amount: int = Field(..., description="Monto en centavos (ej: 5000 para $50.00).")
    currency: str = Field(default="usd", description="Moneda de la transacción.")
    payment_method_type: str = Field(default="card", description="Tipo de método de pago.")
    customer_email: str = Field(..., description="Email del cliente.")
    description: str = Field(..., description="Descripción del producto (ej: '10 créditos').")

# --- Servicio de Voluntarios ---
class TesisClinica(BaseModel):
    """Estructura de la Tesis Clínica generada por la IA."""
    case_id: str
    patient_age: Optional[int]
    patient_gender: Optional[str]
    chief_complaint: str
    history_summary: str
    ai_hypothesis: str = Field(..., description="Diagnóstico más probable de la IA.")
    differential_diagnoses: List[str] = Field(..., description="Lista de diagnósticos diferenciales.")
    diagnostic_plan: str = Field(..., description="Recomendación de plan diagnóstico/tratamiento.")
    ai_disclaimer: str = "Este reporte es generado por Inteligencia Artificial y tiene fines exclusivamente educativos. Debe ser revisado por un profesional humano."

# --- Servicio de Profesionales ---
class ProfessionalRegister(BaseModel):
    """Esquema para el registro de un profesional."""
    email: str = Field(..., description="Email del profesional.")
    name: str = Field(..., description="Nombre completo del profesional.")
    specialty: str = Field(..., description="Especialidad médica (ej: 'Cardiología').")
    
class DebateResult(BaseModel):
    case_id: str
    professional_diagnosis: str = Field(description="El diagnóstico final del profesional.")
    outcome: str = Field(description="Resultado (victory, defeat, draw).")
