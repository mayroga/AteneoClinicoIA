import os
from fastapi import FastAPI, Header, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
from config import settings # Importa la configuración actualizada (incluyendo precios y bypass)

# Asegúrate de haber instalado las dependencias necesarias:
# fastapi, uvicorn, pydantic, pydantic-settings, python-dotenv, google-genai, sendgrid, stripe, psycopg2-binary

# NOTA: Las importaciones de stripe y otros servicios están comentadas 
# para evitar errores de despliegue hasta que el código real se implemente.
# import stripe 
# from sendgrid import SendGridAPIClient

app = FastAPI(
    title="Ateneo Clínico IA Backend",
    version="1.0.0",
    description="Servicio backend para debate IA, pagos y notificaciones."
)

# ==============================================================================
# 1. ESQUEMAS DE DATOS
# ==============================================================================

class TransactionResponse(BaseModel):
    """Esquema de respuesta para las transacciones."""
    status: str = Field(..., description="Estado de la transacción (éxito/fallo).")
    message: str = Field(..., description="Mensaje detallado.")
    amount: Optional[float] = Field(None, description="Monto del cobro aplicado, si hubo.")
    user_type: Optional[str] = Field(None, description="Tipo de usuario para el cobro.")

class EmailData(BaseModel):
    """Esquema para el envío de correos."""
    recipient: str
    subject: str
    body: str

# ==============================================================================
# 2. FUNCIONES DE UTILIDAD (MOCK/Simuladas)
# ==============================================================================

def get_current_user_id(request: Request) -> str:
    """
    Simula la obtención del ID del usuario autenticado (se espera en el encabezado 'X-User-ID').
    """
    # Usamos un encabezado para simular la autenticación.
    user_id = request.headers.get("x-user-id", "anonymous")
    return user_id

async def mock_ai_debate(query: str) -> str:
    """
    Función simulada para el debate con IA usando Google GenAI.
    """
    # Aquí iría el código real para usar settings.google_api_key y llamar a la API de Gemini.
    print(f"Llamando a la IA con query: {query}")
    await asyncio.sleep(1) # Simula latencia
    return f"Respuesta de la IA para '{query}': La evidencia clínica sugiere una aproximación multifacética..."

def mock_send_email(data: EmailData) -> bool:
    """
    Función simulada para enviar correos usando SendGrid.
    """
    # Aquí iría el código real para usar settings.sendgrid_api_key y llamar a SendGrid.
    print(f"Correo simulado enviado a {data.recipient} desde {settings.default_sender_email} con asunto: {data.subject}")
    return True

# def create_payment_intent(amount: float):
#     """Función real de Stripe para crear la intención de pago."""
#     # Aquí iría el código real de Stripe.
#     # stripe.api_key = settings.stripe_secret_key # Asume que tienes una clave secreta de Stripe en config
#     # intent = stripe.PaymentIntent.create(...)
#     # return intent.client_secret
#     pass


# ==============================================================================
# 3. RUTAS DE LA APLICACIÓN
# ==============================================================================

@app.get("/")
def home():
    """Ruta de salud para verificar que el servicio está funcionando."""
    return {"status": "ok", "message": "Ateneo Clínico IA operativo."}

@app.post("/process-transaction/", response_model=TransactionResponse)
async def process_transaction(
    request: Request,
    user_role: str = Header(..., description="Rol del usuario: 'volunteer' o 'professional'. Se espera en 'X-User-Role'."),
):
    """
    Procesa la solicitud de pago, aplicando precios segmentados
    por tipo de usuario y la exención para el desarrollador.
    """
    current_user_id = get_current_user_id(request)
    
    # ----------------------------------------------------------------------
    # LÓGICA DE ACCESO GRATUITO PARA EL DESARROLLADOR (BYPASS)
    # ----------------------------------------------------------------------
    if current_user_id == settings.admin_bypass_key and settings.admin_bypass_key != "":
        return TransactionResponse(
            status="success",
            message=f"ACCESO GRATUITO ILIMITADO: Bypass activado para el usuario {current_user_id}.",
            amount=0.0,
            user_type="Developer (Bypass)"
        )

    # ----------------------------------------------------------------------
    # LÓGICA DE PRECIOS SEGMENTADOS POR TIPO DE USUARIO
    # ----------------------------------------------------------------------
    
    user_role_lower = user_role.lower()
    
    if user_role_lower == 'volunteer':
        price_to_charge = settings.price_volunteer  # $40.00
        user_type_charged = "Voluntario"
    elif user_role_lower == 'professional':
        price_to_charge = settings.price_professional # $149.99
        user_type_charged = "Profesional"
    else:
        # Si no se proporciona un rol válido.
        raise HTTPException(
            status_code=400, 
            detail="Rol de usuario no válido. Debe ser 'volunteer' o 'professional'. Asegúrate de enviar el encabezado 'X-User-Role'."
        )

    # ----------------------------------------------------------------------
    # PROCESAMIENTO DE PAGO REAL (SIMULADO)
    # ----------------------------------------------------------------------
    
    # Aquí es donde usarías la función real de Stripe:
    # client_secret = create_payment_intent(price_to_charge) 
    
    try:
        # Simulamos el éxito del cobro (Reemplazar con lógica de Stripe)
        print(f"Iniciando cobro de {price_to_charge} USD para {user_type_charged}...")
        
        return TransactionResponse(
            status="success",
            message=f"Cobro de {price_to_charge} USD iniciado con éxito para el rol de {user_type_charged}. Se requiere confirmación de Stripe.",
            amount=price_to_charge,
            user_type=user_type_charged
        )
    except Exception as e:
        # Manejo de errores de Stripe
        raise HTTPException(status_code=500, detail=f"Fallo al procesar el pago: {str(e)}")


@app.post("/debate/")
async def debate_ai(query: str):
    """Permite a los usuarios interactuar con el modelo de IA (Gemini)."""
    if not settings.google_api_key:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado (Falta GOOGLE_API_KEY).")
    
    response = await mock_ai_debate(query)
    return {"query": query, "response": response}

@app.post("/send-notification/")
async def send_notification(data: EmailData):
    """Envía notificaciones por correo electrónico a los usuarios."""
    if not settings.sendgrid_api_key:
        raise HTTPException(status_code=503, detail="Servicio de correo no configurado (Falta SENDGRID_API_KEY).")
    
    if mock_send_email(data):
        return {"status": "success", "message": "Correo enviado con éxito desde " + settings.default_sender_email}
    else:
        raise HTTPException(status_code=500, detail="Fallo al enviar el correo.")
