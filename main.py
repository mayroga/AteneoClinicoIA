import os
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import asyncio

# --- IMPORTACIONES DE SERVICIOS REALES ---
from configuracion import settings # Configuración con claves de producción
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import stripe # Cliente real de Stripe para cobros
from google import genai # Cliente real de Google GenAI para IA
import psycopg2 # Cliente real para PostgreSQL
from psycopg2 import OperationalError
from starlette.responses import JSONResponse # Necesario para devolver la URL de Stripe

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Ateneo Clínico IA Backend",
    version="1.0.0",
    description="Servicio backend para debate IA, pagos y notificaciones."
)

# Inicializar cliente de Stripe (Se ejecuta al iniciar el servidor)
try:
    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key
        print("INFO: Stripe inicializado con clave secreta.")
    else:
        print("ADVERTENCIA: Stripe secret key no configurada. Los pagos reales fallarán.")
except Exception as e:
    print(f"ERROR: Fallo al inicializar Stripe: {e}")

# ==============================================================================
# 1. ESQUEMAS DE DATOS
# ==============================================================================

class TransactionResponse(BaseModel):
    """Esquema de respuesta para las transacciones (usado para Payment Intent)."""
    status: str = Field(..., description="Estado de la transacción (éxito/fallo).")
    message: str = Field(..., description="Mensaje detallado.")
    client_secret: Optional[str] = Field(None, description="Client Secret de Stripe para procesar el pago.")
    amount: Optional[float] = Field(None, description="Monto del cobro aplicado, si hubo.")
    user_type: Optional[str] = Field(None, description="Tipo de usuario para el cobro.")

class EmailData(BaseModel):
    """Esquema para el envío de correos o solicitud de email."""
    email: EmailStr = Field(..., description="Dirección de correo electrónico del usuario.")
    subject: Optional[str] = None
    body: Optional[str] = None

class DebateData(BaseModel):
    """Esquema para el debate con IA."""
    query: str
    history: Optional[list] = None 

# ==============================================================================
# 2. FUNCIONES DE SERVICIO REAL
# ==============================================================================

def get_current_user_id(request: Request) -> str:
    """Obtiene el ID del usuario del encabezado 'X-User-ID'."""
    user_id = request.headers.get("x-user-id", "anonymous")
    return user_id

def create_payment_intent(amount: float, currency: str = 'usd') -> dict:
    """
    Función REAL de Stripe para crear una intención de pago (Payment Intent).
    Esto se usaría típicamente para Stripe Elements (cobro en la app).
    """
    if not settings.stripe_secret_key:
        raise Exception("Clave Secreta de Stripe no configurada. Cobro real deshabilitado.")
    
    try:
        # Uso del cliente Stripe inicializado
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Stripe usa centavos
            currency=currency,
            automatic_payment_methods={"enabled": True},
        )
        return {"client_secret": intent.client_secret, "amount": amount}
        
    except Exception as e:
        print(f"ERROR en Stripe al crear intención: {e}")
        # Aseguramos que el error de Stripe se eleve correctamente
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Fallo al crear intención de pago en Stripe: {str(e)}"
        )


async def ai_debate_service(query: str) -> str:
    """
    Función REAL para el debate con IA usando Google GenAI.
    """
    if not settings.google_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                            detail="Servicio de IA no configurado (Falta GOOGLE_API_KEY).")

    try:
        # Inicializar el cliente
        client = genai.Client(api_key=settings.google_api_key)
        system_instruction = ("Eres un experto en el ateneo clínico, especializado en debatir casos complejos "
                              "y proporcionar un análisis médico riguroso basado en evidencia.")

        # La llamada a la API de Gemini se realiza dentro de un hilo para no bloquear el bucle de eventos
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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                            detail=f"Fallo en el servicio de IA: {str(e)}")


def send_email_service(data: EmailData) -> bool:
    """
    Función REAL para enviar correos usando SendGrid.
    """
    if not settings.sendgrid_api_key:
        print("ADVERTENCIA: SendGrid API Key no está configurada.")
        return False
        
    message = Mail(
        from_email=settings.default_sender_email,
        to_emails=data.email, # Usamos data.email
        subject=data.subject,
        html_content=data.body
    )
    
    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(message)
        return response.status_code in [200, 202]
    except Exception as e:
        print(f"ERROR: Fallo al enviar correo con SendGrid: {str(e)}")
        return False

def check_db_connection() -> bool:
    """
    Verifica la conexión real a la base de datos PostgreSQL.
    """
    if not settings.database_url:
        return False
    
    try:
        conn = psycopg2.connect(settings.database_url, connect_timeout=5)
        conn.close()
        return True
    except OperationalError as e:
        print(f"ERROR de conexión a DB: {e}")
        return False
    except Exception as e:
        print(f"ERROR inesperado de DB: {e}")
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
            detail="Fallo al conectar con la base de datos PostgreSQL. Verifica DATABASE_URL en Render."
        )

# ----------------------------------------------------
# FLUJO VOLUNTARIO - STRIPE CHECKOUT SESSION (Redirección simple de pago)
# ----------------------------------------------------

@app.post("/api/v1/volunteer/create-checkout-session")
async def create_checkout_session(data: EmailData):
    """
    Crea una sesión de Stripe Checkout para la cuota de Voluntario 
    y devuelve la URL para redirigir al usuario.
    """
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de Stripe no configurado (Falta STRIPE_SECRET_KEY)."
        )

    try:
        # Precio del voluntario en centavos (Stripe usa centavos)
        price_in_cents = int(settings.price_volunteer * 100)
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Cuota de Voluntario - Tesis Clínica IA',
                        'description': 'Generación de Tesis Clínica y activación del debate médico.',
                    },
                    'unit_amount': price_in_cents, 
                },
                'quantity': 1,
            }],
            mode='payment',
            
            # URLs de redirección tras el pago o cancelación.
            success_url=f"{settings.app_base_url}/volunteer/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.app_base_url}/volunteer/cancel",
            
            # Datos del cliente para pre-rellenar el formulario de Stripe
            customer_email=data.email,
            
            # Metadata para vincular la sesión de Stripe con la aplicación
            metadata={
                'user_email': data.email,
                'user_type': 'volunteer',
            }
        )
        
        # Devolvemos la URL de la sesión de Stripe al frontend
        return JSONResponse({"url": session.url})
        
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al iniciar el pago con Stripe. Por favor, inténtalo de nuevo."
        )

# ----------------------------------------------------
# FLUJO PROFESIONAL - STRIPE PAYMENT INTENT (Se mantiene la lógica original del usuario, renombrada)
# ----------------------------------------------------

@app.post("/api/v1/professional/create-payment-intent/", response_model=TransactionResponse)
async def create_professional_payment_intent(
    request: Request,
    user_role: str = Header(..., description="Rol del usuario: 'volunteer' o 'professional'. Se espera en 'X-User-Role'."),
):
    """
    Procesa la solicitud de pago para Profesionales usando Payment Intent (para Stripe Elements).
    """
    current_user_id = get_current_user_id(request)
    
    # LÓGICA DE ACCESO GRATUITO PARA EL DESARROLLADOR (BYPASS)
    if current_user_id == settings.admin_bypass_key and settings.admin_bypass_key != "":
        return TransactionResponse(
            status="success",
            message=f"ACCESO GRATUITO ILIMITADO: Bypass activado para el usuario {current_user_id}.",
            amount=0.0,
            user_type="Developer (Bypass)",
            client_secret="BYPASS_SECRET_000"
        )

    # LÓGICA DE PRECIOS SEGMENTADOS POR TIPO DE USUARIO
    user_role_lower = user_role.lower()
    
    if user_role_lower == 'professional':
        price_to_charge = settings.price_professional
        user_type_charged = "Profesional"
    else:
        # Se pide usar el endpoint de Checkout para voluntarios
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Rol de usuario no válido para este endpoint. Use el endpoint de checkout para 'volunteer'."
        )

    # PROCESAMIENTO DE PAGO REAL (STRIPE)
    try:
        payment_info = create_payment_intent(price_to_charge) 
        
        return TransactionResponse(
            status="success",
            message=f"Intención de pago de {price_to_charge} USD creada con éxito para {user_type_charged}.",
            amount=price_to_charge,
            user_type=user_type_charged,
            client_secret=payment_info['client_secret']
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Fallo al procesar el pago: {str(e)}")


@app.post("/debate/")
async def debate_ai(data: DebateData):
    """Permite a los usuarios interactuar con el modelo de IA (Gemini)."""
    # Llama a la función REAL de debate con Gemini
    response = await ai_debate_service(data.query)
    return {"query": data.query, "response": response}

@app.post("/send-notification/")
async def send_notification(data: EmailData):
    """Envía notificaciones por correo electrónico a los usuarios."""
    # Llama a la función de envío de correo real
    if send_email_service(data):
        return {"status": "success", "message": "Correo enviado con éxito usando SendGrid."}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Fallo al enviar el correo con SendGrid. Revisa la clave o el email del remitente."
        )
