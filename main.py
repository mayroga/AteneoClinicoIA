import os
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
import asyncio
import json 

# --- IMPORTACIONES DE SERVICIOS REALES ---
# Asegúrate de que 'configuracion' es el nombre correcto de tu módulo de settings
from configuracion import settings 
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import stripe # Cliente real de Stripe para cobros
from google import genai # Cliente real de Google GenAI para IA
import psycopg2 
from psycopg2 import OperationalError
from starlette.responses import JSONResponse 

# Importar utilidades de la base de datos
import database 
# Importar servicios de lógica
import professional_service 
import volunteer_service 

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
# INICIALIZACIÓN DE LA BASE DE DATOS
# ==============================================================================

@app.on_event("startup")
def startup_event():
    """Llama a la verificación y creación de tablas al iniciar el servidor."""
    print("INFO: Iniciando verificación y creación de tablas de base de datos...")
    # Llama a la función del módulo database
    database.create_tables()
    print("INFO: Inicialización de base de datos completada.")


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

class WaiverAcceptRequest(BaseModel):
    """Modelo para aceptar términos legales (Waiver)."""
    email: EmailStr
    user_type: str = Field(..., description="Tipo de usuario: 'volunteer' o 'professional'.")

class ProfessionalRegisterRequest(BaseModel):
    """Esquema para el registro de un profesional."""
    email: EmailStr = Field(..., description="Email del profesional.")
    name: str = Field(..., description="Nombre completo del profesional.")
    specialty: str = Field(..., description="Especialidad médica (ej: 'Cardiología').")

class DebateData(BaseModel):
    """Esquema para el debate con IA."""
    query: str
    history: Optional[list] = None 

class ProfessionalProfile(BaseModel):
    email: EmailStr
    name: str
    specialty: str
    credits: int
    score_refutation: int
    is_new: Optional[bool] = None
    
# ----------------------------------------------------
# Esquema de Input para el Voluntario (Ahora con imagen)
# ----------------------------------------------------
class ClinicalCaseInput(BaseModel):
    """Esquema para la entrada de datos del caso clínico (texto e imagen) por el voluntario."""
    volunteer_email: EmailStr = Field(..., description="Email del voluntario que sube el caso.")
    clinical_data: str = Field(..., description="Texto completo de la historia clínica o resumen.")
    image_path: str = Field(..., description="Ruta local o URL a la imagen de apoyo (Radiografía, ECG, etc.).")


# ==============================================================================
# 2. FUNCIONES DE SERVICIO REAL
# ==============================================================================

def get_current_user_id(request: Request) -> str:
    """Obtiene el ID del usuario del encabezado 'X-User-ID'."""
    user_id = request.headers.get("x-user-id", "anonymous")
    return user_id

def create_payment_intent(amount: float, currency: str = 'usd') -> dict:
    """Función REAL de Stripe para crear una intención de pago (Payment Intent)."""
    if not settings.stripe_secret_key:
        raise Exception("Clave Secreta de Stripe no configurada. Cobro real deshabilitado.")
    
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100), 
            currency=currency,
            automatic_payment_methods={"enabled": True},
        )
        return {"client_secret": intent.client_secret, "amount": amount}
    except Exception as e:
        print(f"ERROR en Stripe al crear intención: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Fallo al crear intención de pago en Stripe: {str(e)}"
        )


async def ai_debate_service(query: str) -> str:
    """Función REAL para el debate con IA usando Google GenAI."""
    if not settings.google_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                            detail="Servicio de IA no configurado (Falta GOOGLE_API_KEY).")

    try:
        client = genai.Client(api_key=settings.google_api_key)
        system_instruction = ("Eres un experto en el ateneo clínico, especializado en debatir casos complejos "
                              "y proporcionar un análisis médico riguroso basado en evidencia.")

        # Usar asyncio.to_thread para correr el cliente síncrono de Gemini sin bloquear FastAPI
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
    """Función REAL para enviar correos usando SendGrid."""
    if not settings.sendgrid_api_key:
        print("ADVERTENCIA: SendGrid API Key no está configurada.")
        return False
        
    message = Mail(
        from_email=settings.default_sender_email,
        to_emails=data.email, 
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
    """Verifica la conexión real a la base de datos PostgreSQL usando la utilidad del módulo database."""
    conn = database.get_db_connection()
    if conn:
        conn.close()
        return True
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
# 3.1 GESTIÓN DE ACEPTACIÓN LEGAL (WAIVER)
# ----------------------------------------------------

@app.post("/waiver/accept", status_code=status.HTTP_200_OK)
async def accept_waiver(data: WaiverAcceptRequest):
    """
    Registra la aceptación de los términos legales (Waiver) por parte del usuario
    en la base de datos.
    """
    if data.user_type.lower() not in ['volunteer', 'professional']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="El tipo de usuario debe ser 'volunteer' o 'professional'."
        )
        
    try:
        success = database.insert_waiver(data.email, data.user_type.lower())
        
        if success:
            return {"status": "success", "message": f"Términos aceptados. Usuario {data.user_type} registrado correctamente."}
        else:
            return {"status": "info", "message": f"Términos ya aceptados para el email {data.email}. Continuando."}

    except Exception as e:
        print(f"ERROR en /waiver/accept: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al registrar la aceptación de términos."
        )

# ----------------------------------------------------
# 3.2 REGISTRO DE PROFESIONALES (USA EL SERVICIO)
# ----------------------------------------------------

@app.post("/professional/register", response_model=ProfessionalProfile, status_code=status.HTTP_201_CREATED)
async def register_professional_user(data: ProfessionalRegisterRequest):
    """
    Registra o actualiza a un profesional, verificando el waiver y asignando 1 crédito inicial.
    """
    try:
        # Usamos la lógica de professional_service para manejar el waiver y el crédito
        result = professional_service.register_professional(
            email=data.email, 
            name=data.name, 
            specialty=data.specialty
        )
        
        if result is None:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Error interno al conectar con la base de datos."
            )

        if 'error' in result:
            # Manejar el error de waiver no aceptado
            if 'Waiver no aceptado' in result['error']:
                 raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, 
                    detail=result['error']
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=result['error']
            )

        # Si no hubo error, devolvemos el perfil completo
        return ProfessionalProfile(**result)
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"ERROR en /professional/register: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al registrar al profesional."
        )

# ----------------------------------------------------
# 3.3 ASIGNACIÓN DE CASOS PARA DEBATE (PROFESIONALES)
# ----------------------------------------------------
@app.post("/professional/get-case/{email}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
async def get_case_for_debate(email: EmailStr):
    """
    Descuenta 1 crédito del profesional y le asigna un caso clínico disponible para debate.
    """
    try:
        result = professional_service.get_debate_case(email)

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Error interno al procesar la solicitud del caso."
            )
            
        if 'error' in result:
            # Manejar errores de negocio (créditos insuficientes, no hay casos)
            status_code = status.HTTP_402_PAYMENT_REQUIRED if 'Créditos insuficientes' in result['error'] else status.HTTP_404_NOT_FOUND
            raise HTTPException(
                status_code=status_code, 
                detail=result['error']
            )

        # La respuesta es el reporte de IA (JSONB) más el case_id
        return result
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"ERROR en /professional/get-case: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al intentar asignar el caso."
        )

# ----------------------------------------------------
# 3.4 FLUJO VOLUNTARIO - GENERACIÓN DE TESIS CLÍNICA (VISION)
# ----------------------------------------------------

@app.post("/volunteer/generate-thesis", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def volunteer_generate_thesis(data: ClinicalCaseInput):
    """
    Recibe la historia clínica y la imagen, genera la Tesis Clínica estructurada con 
    la IA (Vision) y la guarda en la DB.
    """
    # Nota Importante: La función del servicio ahora es SÍNCRONA, por eso la ruta también lo es (def).

    # VALIDACIÓN DE RUTA DE IMAGEN (temporal)
    if not os.path.exists(data.image_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo de imagen no existe en la ruta especificada: {data.image_path}. "
                   "En un entorno real, esta ruta sería la ubicación temporal del archivo subido."
        )
    
    try:
        # Llama a la función del nuevo servicio síncrono
        ai_report_model = volunteer_service.process_volunteer_case(
            email=data.volunteer_email,
            history_text=data.clinical_data,
            image_path=data.image_path
        )

        if ai_report_model is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Error en la generación de la tesis clínica o al guardar en la base de datos. Revisa logs."
            )
            
        # El modelo Pydantic se convierte a dict automáticamente para la respuesta
        return ai_report_model.model_dump()

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"ERROR en /volunteer/generate-thesis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al generar la tesis clínica."
        )
        
# ----------------------------------------------------
# 3.5 FLUJO VOLUNTARIO - OBTENER REPORTE Y MENSAJE VIRAL (NUEVO)
# ----------------------------------------------------

@app.get("/volunteer/report-and-message/{email}", response_model=Dict[str, Any], status_code=status.HTTP_200_OK)
def get_report_and_viral_message_route(email: EmailStr):
    """
    Recupera el último caso generado por el voluntario y su mensaje viral asociado.
    """
    # La función del servicio es SÍNCRONA.
    result = volunteer_service.get_volunteer_report_and_viral_message(email)
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró un caso clínico reciente para el email: {email}."
        )
        
    return result


# ----------------------------------------------------
# 3.6 FLUJO VOLUNTARIO - STRIPE CHECKOUT SESSION 
# ----------------------------------------------------

@app.post("/api/v1/volunteer/create-checkout-session")
async def create_checkout_session(data: EmailData):
    """Crea una sesión de Stripe Checkout para la cuota de Voluntario."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio de Stripe no configurado (Falta STRIPE_SECRET_KEY)."
        )

    try:
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
            success_url=f"{settings.app_base_url}/volunteer/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.app_base_url}/volunteer/cancel",
            customer_email=data.email,
            metadata={
                'user_email': data.email,
                'user_type': 'volunteer',
            }
        )
        
        return JSONResponse({"url": session.url})
        
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al iniciar el pago con Stripe. Por favor, inténtalo de nuevo."
        )

# ----------------------------------------------------
# 3.7 FLUJO PROFESIONAL - STRIPE PAYMENT INTENT 
# ----------------------------------------------------

@app.post("/api/v1/professional/create-payment-intent/", response_model=TransactionResponse)
async def create_professional_payment_intent(
    request: Request,
    user_role: str = Header(..., description="Rol del usuario: 'volunteer' o 'professional'. Se espera en 'X-User-Role'."),
):
    """Procesa la solicitud de pago para Profesionales usando Payment Intent (para Stripe Elements)."""
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
