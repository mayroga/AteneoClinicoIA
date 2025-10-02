import os
# Importamos FastAPI y clases relacionadas
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
# Importamos la configuración que contiene la ADMIN_BYPASS_KEY
from config import settings 

# Asegúrate de que las librerías necesarias (stripe, google-genai, sendgrid)
# estén listadas en tu archivo requirements.txt

# Inicialización de la aplicación FastAPI
app = FastAPI(title="Ateneo Clínico IA Backend")

# --- Modelos de Pydantic ---

class PaymentDetails(BaseModel):
    """Modelo para recibir los detalles de un intento de pago."""
    amount: float
    currency: str = "usd"
    description: str

class EmailDetails(BaseModel):
    """Modelo para recibir los detalles de un envío de correo."""
    recipient: str
    subject: str
    content: str
    
class AiPrompt(BaseModel):
    """Modelo para recibir la consulta de debate o asistencia."""
    prompt: str


# --- Servicios de Autenticación Ficticios ---

# NOTA IMPORTANTE: Esta es una función simulada. 
# En una aplicación real, esta función debe integrarse con tu sistema 
# de autenticación (JWT, Firebase Auth, etc.) para obtener el ID real del usuario.
def get_current_user_id(auth_token: str = "token_ejemplo") -> str:
    """
    Obtiene el ID del usuario actual. Si el token coincide con la clave de bypass
    o estamos en desarrollo, devuelve la clave de administrador.
    """
    
    # 1. Modo de prueba o si el token es la clave de bypass
    # Se asume que el token de autenticación del administrador será igual a la clave.
    if os.getenv("ENVIRONMENT") == "development" or auth_token == settings.admin_bypass_key:
         # Retorna la clave de bypass si está configurada, sino un ID por defecto.
         return settings.admin_bypass_key if settings.admin_bypass_key else "dev_id_default"
    
    # 2. Lógica de producción: ID de usuario normal
    return "usuario_normal_45678" 

# --- Rutas de la Aplicación ---

@app.get("/")
async def root():
    """Ruta de prueba simple para verificar que el servidor está activo."""
    return {"message": "¡Servidor Ateneo Clínico IA funcionando! URL Base: " + settings.app_base_url}

@app.post("/process-transaction/")
async def process_transaction(
    details: PaymentDetails, 
    current_user_id: str = Depends(get_current_user_id) 
):
    """
    Procesa una transacción. El cobro se omite si el ID del usuario coincide 
    con la ADMIN_BYPASS_KEY.
    """
    
    # 1. Lógica de acceso gratuito / ilimitado (ADMIN_BYPASS_KEY)
    # Verifica si el ID del usuario actual es igual a la clave de administrador configurada
    if current_user_id == settings.admin_bypass_key and settings.admin_bypass_key:
        print(f"Clave de bypass de administrador detectada ({current_user_id}). Pago OMITIDO.")
        return {
            "status": "success", 
            "message": "Transacción completada, acceso ilimitado concedido (ADMIN BYPASS).",
            "transaction_id": "ADMIN_FREE_ACCESS"
        }

    # 2. Lógica de pago real (Solo para usuarios normales)
    try:
        # Aquí se integraría la llamada real al API de Stripe 
        # (ej: payment_intent = stripe_service.create_payment_intent(...))
        
        # Simulación del proceso de pago:
        payment_intent_id = f"pi_REAL_{int(details.amount * 100)}_{current_user_id}"
        
        return {
            "status": "success",
            "message": "Pago procesado con éxito usando Stripe.",
            "transaction_id": payment_intent_id
        }

    except Exception as e:
        # Manejo de errores de pago
        raise HTTPException(status_code=500, detail=f"Error al procesar el pago: {e}")

# --- Rutas de IA y Correo (Ejemplos de integración) ---

@app.post("/debate/")
async def handle_debate(data: AiPrompt):
    """Maneja las interacciones de debate o asistencia con Google GenAI."""
    # Lógica para llamar al modelo Gemini usando settings.google_api_key
    # client = genai.Client(api_key=settings.google_api_key)
    # response = client.models.generate_content(...)
    
    return {
        "response": f"AI está procesando tu consulta: '{data.prompt}'.",
        "service": "Google GenAI (Gemini)"
    }

@app.post("/send-mail/")
async def send_mail_route(data: EmailDetails):
    """Envía un correo usando SendGrid."""
    # Lógica para SendGrid con settings.sendgrid_api_key
    # from sendgrid import SendGridAPIClient
    # sg = SendGridAPIClient(settings.sendgrid_api_key)
    
    return {
        "status": "success", 
        "message": f"Correo a {data.recipient} enviado desde {settings.default_sender_email}.",
        "subject": data.subject
    }
