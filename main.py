import os
import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai as google_genai 
# O, la forma más común, directamente desde el paquete:
from google.generativeai import Client 
from dotenv import load_dotenv

# Cargar variables de entorno (útil para desarrollo local, Render las inyecta en producción)
load_dotenv() 

# --- Inicialización de Clientes ---
# Reemplaza estas inicializaciones si ya las tienes en otro archivo de config.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Solo inicializamos Gemini si la clave está presente (para evitar fallos al inicio)
if GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        GEMINI_MODEL = "gemini-2.5-flash"
    except Exception as e:
        print(f"Error al inicializar cliente Gemini: {e}")
        gemini_client = None
else:
    gemini_client = None

app = FastAPI()

# --- Configuración CORS CRÍTICA ---
# Permite que el frontend (u otros dominios) se conecte a esta API
origins = [
    "*", # Permite todos los orígenes. AJUSTAR ESTO EN PRODUCCIÓN A TU DOMINIO DE FRONTEND
    # Ejemplo: "https://ateneoclinicoia.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas Pydantic ---
class AdminKey(BaseModel):
    admin_key: str

class CasePrompt(BaseModel):
    prompt: str
    role: str # Nivel de suscripción o 'professional'


# ==========================================================
# ENDPOINT 1: VALIDACIÓN DE ACCESO DE ADMINISTRADOR (/api/admin-auth)
# ==========================================================
@app.post("/api/admin-auth")
async def admin_auth(key_data: AdminKey):
    """Verifica si la clave enviada coincide con la ADMIN_BYPASS_KEY de Render."""
    
    if not ADMIN_BYPASS_KEY:
        # Fallo de configuración si la variable no existe en Render
        raise HTTPException(status_code=500, detail="Clave de bypass no configurada en el servidor (ADMIN_BYPASS_KEY).")
    
    if key_data.admin_key == ADMIN_BYPASS_KEY:
        return {"success": True, "message": "Autenticación de administrador exitosa.", "score": 9999}
    else:
        return {"success": False, "message": "Clave de acceso incorrecta."}


# ==========================================================
# ENDPOINT 2: LLAMADA AL SERVICIO DE IA (GEMINI) (/api/analizar-caso)
# ==========================================================
@app.post("/api/analizar-caso")
async def analyze_case(case_data: CasePrompt):
    """Llama a Gemini para el análisis clínico usando la clave."""
    
    if not gemini_client:
        raise HTTPException(status_code=503, detail="El servicio de IA (Gemini) no está inicializado. Revisa la GEMINI_API_KEY.")
        
    prompt = (
        f"Analiza el siguiente caso clínico para un profesional de la salud con nivel de suscripción '{case_data.role}'. "
        f"Genera un resumen, un diagnóstico diferencial y un plan de acción. Descripción del caso: {case_data.prompt}"
    )
    
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        
        # El texto de respuesta se envía al frontend
        return {"success": True, "response_text": response.text}
        
    except Exception as e:
        print(f"Error en la llamada a Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo en el servicio de Inteligencia Artificial: {e}")


# ==========================================================
# ENDPOINT 3: CREACIÓN DE SESIÓN STRIPE (/api/checkout)
# ==========================================================
class CheckoutItem(BaseModel):
    case_id: str
    case_description: str
    # Se podría incluir aquí el nombre del usuario, etc.

@app.post("/api/checkout")
async def create_checkout_session(request: Request, item: CheckoutItem):
    """Crea una sesión de pago de Stripe para el voluntario."""
    
    # Obtener la URL base dinámicamente o usar la variable de entorno
    BASE_URL = str(request.base_url).strip('/')
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'Análisis de Caso Clínico Voluntario'},
                    'unit_amount': 5000, # $50.00 USD
                },
                'quantity': 1,
            }],
            mode='payment',
            metadata={
                'case_id': item.case_id,
                'case_description': item.case_description,
                'user_id': item.case_id.split('_')[0] # Ejemplo de metadato
            },
            # CRÍTICO: Redirección DEBE coincidir con una URL de tu dominio (BASE_URL)
            success_url=f"{BASE_URL}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/cancel.html",
        )
        
        return {"success": True, "checkout_url": checkout_session.url}
        
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo al iniciar el servicio de pagos: {e}")


# ==========================================================
# ENDPOINT 4: WEBHOOK DE STRIPE (Añadir la ruta para el Webhook aquí)
# ==========================================================
# Aquí es donde Stripe notifica al backend que el pago se completó. 
# ESTA RUTA DEBE ESTAR EXPUESTA Y CONFIGURADA EN EL PANEL DE STRIPE.
# (La implementación real de Webhook requiere manejo de firma y base de datos, 
# pero se deja el esqueleto para indicar su criticidad).

# @app.post("/api/stripe-webhook")
# async def stripe_webhook(request: Request):
#     # 1. Obtener la firma y el cuerpo del evento
#     # 2. Verificar la firma (SEGURIDAD)
#     # 3. Procesar el evento (checkout.session.completed)
#     # 4. Si el pago es OK, obtener case_id de los metadatos y 
#     # 5. Llamar a Gemini para analizar el caso y guardar el resultado en la BD.
#     # 6. Marcar el caso como "Analizado" en la BD.
#     return {"status": "success"}
