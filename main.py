import os
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

# --- IMPORTACIONES DE SERVICIOS REALES ---
from config import settings # Importa la configuración (precios, bypass, claves)
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import stripe # NECESARIO para cobros (Asegúrate que la dependencia 'stripe' esté instalada)
from google import genai # NECESARIO para IA (Asegúrate que la dependencia 'google-genai' esté instalada)
import psycopg2 # NECESARIO para PostgreSQL (Asegúrate que la dependencia 'psycopg2-binary' esté instalada)

app = FastAPI(
    title="Ateneo Clínico IA Backend",
    version="1.0.0",
    description="Servicio backend para debate IA, pagos y notificaciones."
)

# Inicializar cliente de Stripe (asumiendo que tienes STRIPE_SECRET_KEY en settings)
# Nota: La clave secreta de Stripe DEBE estar en tu config.py y en Render.
# settings.stripe_secret_key = Field(default="", description="Clave Secreta de Stripe para cobros.") 
try:
    # Esto inicializará la API de Stripe si la clave está disponible
    # stripe.api_key = settings.stripe_secret_key # Descomentar cuando la clave esté en settings
    pass # Mantener comentado hasta que config.py se actualice con la clave secreta de Stripe
except Exception:
    print("Advertencia: No se pudo inicializar Stripe. El cobro real está deshabilitado.")

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

class DebateData(BaseModel):
    """Esquema para el debate con IA."""
    query: str
    history: Optional[list] = None # Para historial de conversación

# ==============================================================================
# 2. FUNCIONES DE SERVICIO REAL
# ==============================================================================

def get_current_user_id(request: Request) -> str:
    """
    Simula la obtención del ID del usuario autenticado (se espera en el encabezado 'X-User-ID').
    """
    user_id = request.headers.get("x-user-id", "anonymous")
    return user_id

def create_payment_intent(amount: float, currency: str = 'usd') -> dict:
    """
    Función REAL de Stripe para crear una intención de pago.
    ***NOTA: Reemplazar el bloque 'try' por el código real de la API de Stripe.***
    """
    
    # Aquí iría la validación de la clave secreta de Stripe
    # if not stripe.api_key:
    #    raise Exception("Stripe API Key no configurada.")
    
    try:
        # --- CÓDIGO REAL DE STRIPE (Simulado para evitar crash si falta la clave) ---
        
        # intent = stripe.PaymentIntent.create(
        #     amount=int(amount * 100),  # Stripe usa centavos
        #     currency=currency,
        #     automatic_payment_methods={"enabled": True},
        # )
        # return {"client_secret": intent.client_secret, "amount": amount}
        
        # SIMULACIÓN DETALLADA: Si no tienes la clave secreta en settings.
        return {
            "client_secret": f"pi_mock_{amount}", 
            "amount": amount, 
            "warning": "Payment simulated. Add Stripe Secret Key to enable real payments."
        }

    except Exception as e:
        print(f"ERROR en Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo al crear intención de pago en Stripe: {str(e)}")


async def ai_debate_service(query: str) -> str:
    """
    Función REAL para el debate con IA usando Google GenAI.
    """
    if not settings.google_api_key:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado.")

    try:
        # Inicializar el cliente
        client = genai.Client(api_key=settings.google_api_key)
        
        # Mensaje de sistema (Define el rol de la IA)
        system_instruction = ("Eres un experto en el ateneo clínico, especializado en debatir casos complejos "
                              "y proporcionar un análisis médico riguroso basado en evidencia.")

        # Llamada a la API de Gemini
        response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-2.5-flash',
            contents=[query],
            config={
                "system_instruction": system_instruction,
                "temperature": 0.7 
            }
        )
        return response.text
    except Exception as e:
        print(f"ERROR en Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo en el servicio de IA: {str(e)}")


def send_email_service(data: EmailData) -> bool:
    """
    Función REAL para enviar correos usando SendGrid.
    """
    if not settings.sendgrid_api_key:
        print("ADVERTENCIA: SendGrid API Key no está configurada.")
        return False
        
    message = Mail(
        from_email=settings.default_sender_email,
        to_emails=data.recipient,
        subject=data.subject,
        html_content=data.body
    )
    
    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(message)
        print(f"Correo enviado. Estado: {response.status_code}")
        return response.status_code in [200, 202]
    except Exception as e:
        print(f"ERROR: Fallo al enviar correo con SendGrid: {str(e)}")
        return False

def check_db_connection() -> bool:
    """
    Verifica la conexión a la base de datos PostgreSQL.
    """
    if not settings.database_url:
        print("ADVERTENCIA: DATABASE_URL no está configurada.")
        return False
    
    try:
        # Intenta establecer una conexión
        conn = psycopg2.connect(settings.database_url, connect_timeout=5)
        conn.close()
        return True
    except Exception as e:
        print(f"ERROR: Fallo de conexión a DB: {e}")
        return False


# ==============================================================================
# 3. RUTAS DE LA APLICACIÓN
# ==============================================================================

@app.get("/")
def home():
    """Ruta de salud para verificar que el servicio está funcionando."""
    return {"status": "ok", "message": "Ateneo Clínico IA operativo."}

@app.get("/db-health/", status_code=status.HTTP_200_OK)
def db_health():
    """Ruta para verificar la conexión real a la base de datos."""
    if check_db_connection():
        return {"status": "success", "message": "Conexión a PostgreSQL exitosa."}
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Fallo al conectar con la base de datos PostgreSQL. Verifica DATABASE_URL."
        )


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
        price_to_charge = settings.price_volunteer
        user_type_charged = "Voluntario"
    elif user_role_lower == 'professional':
        price_to_charge = settings.price_professional
        user_type_charged = "Profesional"
    else:
        # Si no se proporciona un rol válido.
        raise HTTPException(
            status_code=400, 
            detail="Rol de usuario no válido. Debe ser 'volunteer' o 'professional'. Asegúrate de enviar el encabezado 'X-User-Role'."
        )

    # ----------------------------------------------------------------------
    # PROCESAMIENTO DE PAGO REAL (STRIPE)
    # ----------------------------------------------------------------------
    
    try:
        # Llama a la función REAL de Stripe para crear una intención de pago
        payment_info = create_payment_intent(price_to_charge) 
        
        return TransactionResponse(
            status="success",
            message=f"Intención de pago de {price_to_charge} USD creada con éxito para {user_type_charged}. Client Secret: {payment_info['client_secret']}",
            amount=price_to_charge,
            user_type=user_type_charged
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        # Manejo de errores de Stripe
        raise HTTPException(status_code=500, detail=f"Fallo al procesar el pago: {str(e)}")


@app.post("/debate/")
async def debate_ai(data: DebateData):
    """Permite a los usuarios interactuar con el modelo de IA (Gemini)."""
    if not settings.google_api_key:
        raise HTTPException(status_code=503, detail="Servicio de IA no configurado (Falta GOOGLE_API_KEY).")
    
    # Llama a la función REAL de debate con Gemini
    response = await ai_debate_service(data.query)
    return {"query": data.query, "response": response}

@app.post("/send-notification/")
async def send_notification(data: EmailData):
    """Envía notificaciones por correo electrónico a los usuarios."""
    if not settings.sendgrid_api_key:
        raise HTTPException(status_code=503, detail="Servicio de correo no configurado (Falta SENDGRID_API_KEY).")
    
    # Llama a la función de envío de correo real
    if send_email_service(data):
        return {"status": "success", "message": "Correo enviado con éxito usando SendGrid."}
    else:
        raise HTTPException(status_code=500, detail="Fallo al enviar el correo con SendGrid.")
