import os
import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# 💡 FIX DEFINITIVO: Esta importación es la que resuelve el error. (Corregido 'erro' a 'error')
from google.generativeai import Client as GeminiClient
from dotenv import load_dotenv

# Cargar variables de entorno (útil para desarrollo local, Render las inyecta en producción)
load_dotenv() 

# --- Inicialización de Clientes y Variables ---
# Asegúrate de que estas variables de entorno (STRIPE_SECRET_KEY, ADMIN_BYPASS_KEY, GEMINI_API_KEY)
# estén configuradas en la consola de Render.
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

gemini_client = None
if GEMINI_API_KEY:
    try:
        # Inicialización usando la clase Client importada correctamente
        gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error al inicializar cliente Gemini: {e}")
        # La API seguirá funcionando, pero el endpoint de IA fallará.

app = FastAPI()

# --- Configuración CORS CRÍTICA ---
origins = [
    # En producción, reemplaza '*' con tu dominio de frontend de Render
    "https://ateneoclinicoia.onrender.com",
    "http://127.0.0.1:5500",
    "*" 
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
    role: str

class CheckoutItem(BaseModel):
    case_id: str
    case_description: str


# ==========================================================
# ENDPOINT 1: VALIDACIÓN DE ACCESO DE ADMINISTRADOR (/api/admin-auth)
# ==========================================================
@app.post("/api/admin-auth")
async def admin_auth(key_data: AdminKey):
    """Verifica si la clave enviada coincide con la ADMIN_BYPASS_KEY de Render."""
    
    if not ADMIN_BYPASS_KEY:
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
    """Llama a Gemini para el análisis clínico."""
    
    if not gemini_client:
        raise HTTPException(status_code=503, detail="El servicio de IA (Gemini) no está inicializado. Revisa la GEMINI_API_KEY.")
        
    prompt = (
        f"Analiza el siguiente caso clínico para un profesional de la salud con nivel de suscripción '{case_data.role}'. "
        f"Genera un resumen, un diagnóstico diferencial y un plan de acción detallado. Descripción del caso: {case_data.prompt}"
    )
    
    try:
        # Uso del cliente inicializado (gemini_client)
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        
        return {"success": True, "response_text": response.text}
        
    except Exception as e:
        print(f"Error en la llamada a Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo en el servicio de Inteligencia Artificial: {e}")


# ==========================================================
# ENDPOINT 3: CREACIÓN DE SESIÓN STRIPE (/api/checkout)
# ==========================================================
@app.post("/api/checkout")
async def create_checkout_session(request: Request, item: CheckoutItem):
    """Crea una sesión de pago de Stripe para el voluntario."""
    
    BASE_URL = str(request.base_url).strip('/') 
    
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="La clave secreta de Stripe no está configurada.")

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
            },
            # CRÍTICO: Estas URL deben existir en tu frontend/servidor estático
            success_url=f"{BASE_URL}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/cancel.html",
        )
        
        return {"success": True, "checkout_url": checkout_session.url}
        
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo al iniciar el servicio de pagos: {e}")
