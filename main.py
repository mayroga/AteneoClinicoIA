import os
import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# 💡 CORRECCIÓN DE IMPORTACIÓN DE GEMINI: 
# Usamos el paquete completo para acceder al objeto Client.
import google.generativeai as genai

# Cargar variables de entorno
load_dotenv() 

# --- Asumiendo la existencia de estos módulos de configuración y rutas ---
# Si estos archivos no existen, el código fallará al importarlos, pero asumimos
# que la estructura del proyecto los requiere.

# Importa las dependencias necesarias
# from routes.auth import router as auth_router
# from routes.volunteer import router as volunteer_router
# from routes.professional import router as professional_router
# from routes.admin import router as admin_router
# from routes.stripe_webhook import router as stripe_webhook_router
# from database import init_db
# from config import APP_NAME

# Dummies para evitar error de NameError en este único archivo
APP_NAME = "Ateneo Clínico IA"
def init_db():
    print("Database initialization placeholder.")
# Asumiendo que las rutas están vacías si no se definen
from fastapi import APIRouter
auth_router = volunteer_router = professional_router = admin_router = stripe_webhook_router = APIRouter()

# --- Inicialización de Clientes y Variables ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ==============================================================
# CONFIGURACIÓN DE CLIENTE GEMINI
# ==============================================================
gemini_client = None
if GEMINI_API_KEY:
    try:
        # Inicialización usando genai.Client()
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("Cliente Gemini inicializado exitosamente.")
    except Exception as e:
        print(f"Error al inicializar cliente Gemini: {e}")
        gemini_client = None
else:
    print("Advertencia: GEMINI_API_KEY no encontrada.")
    gemini_client = None

# ==============================================================
# CONTEXTO DE INICIO Y CIERRE DE LA APLICACIÓN
# ==============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función que se ejecuta cuando la aplicación se inicia para preparar la base de datos.
    """
    print("Initializing Database...")
    init_db() # Llama a la inicialización de DB
    yield
    print("Application shutdown complete.")


# ==============================================================
# INICIALIZACIÓN ÚNICA DE LA APP FASTAPI
# ==============================================================
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan, # Usa el contexto definido arriba
    docs_url=None, # Deshabilita la documentación de /docs por defecto
    redoc_url=None # Deshabilita la documentación de /redoc por defecto
)

# ==============================================================
# CONFIGURACIÓN DE CORS
# ==============================================================
origins = [
    "https://ateneoclinicoia.onrender.com",
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*", # Permite todos los orígenes. AJUSTAR ESTO EN PRODUCCIÓN A TU DOMINIO DE FRONTEND
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================
# CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS
# ==============================================================
# Montar el directorio 'static' para servir archivos como CSS, JS y imágenes
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Schemas Pydantic ---
class AdminKey(BaseModel):
    admin_key: str

class CasePrompt(BaseModel):
    prompt: str
    role: str # Nivel de suscripción o 'professional'

class CheckoutItem(BaseModel):
    case_id: str
    case_description: str
    # Se podría incluir aquí el nombre del usuario, etc.


# ==============================================================
# RUTA RAÍZ: SIRVE EL ARCHIVO HTML PRINCIPAL
# ==============================================================
@app.get("/", tags=["Root"], response_class=HTMLResponse)
async def serve_frontend():
    """Sirve el archivo HTML principal de la aplicación para el frontend."""
    # Asegúrate de que 'index.html' esté en el mismo directorio que main.py o en 'static'
    html_file_path = "index.html"
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        # En entornos de Render/producción, quizás debas referenciar StaticFiles
        # Si index.html está en 'static' usa: StaticFiles(directory="static").get_response(...)
        return HTMLResponse(
            content="<h1>Error: Archivo index.html no encontrado en la ruta de la aplicación.</h1>",
            status_code=500
        )


# ==============================================================
# RUTAS DE DOCUMENTACIÓN
# ==============================================================
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """Sirve la página HTML de Redoc."""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Redoc"
    )

@app.get(app.openapi_url, include_in_schema=False)
async def get_open_api_endpoint():
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )


# ==============================================================
# INCLUSIÓN DE ROUTERS CON PREFIJO GLOBAL /api
# ==============================================================
# Se incluyen las rutas de los otros archivos (auth, volunteer, professional, admin, webhook)
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/api/volunteer", tags=["Volunteer"])
app.include_router(professional_router, prefix="/api/professional", tags=["Professional"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(stripe_webhook_router, prefix="/api") # Webhook de Stripe queda en /api/stripe/webhook

# ==============================================================
# ENDPOINTS DEFINIDOS EN MAIN.PY
# ==============================================================

@app.get("/api", tags=["Status"])
async def status_check():
    """Mensaje de prueba para verificar que la API está en línea."""
    return {"message": "✅ API Ateneo Clínico IA en línea y funcionando correctamente"}


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
@app.post("/api/checkout")
async def create_checkout_session(request: Request, item: CheckoutItem):
    """Crea una sesión de pago de Stripe para el voluntario."""
    
    # Obtener la URL base dinámicamente o usar la variable de entorno
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
            # CRÍTICO: Redirección DEBE coincidir con una URL de tu dominio (BASE_URL)
            success_url=f"{BASE_URL}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/cancel.html",
        )
        
        return {"success": True, "checkout_url": checkout_session.url}
        
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo al iniciar el servicio de pagos: {e}")

# ==========================================================
# ENDPOINT 4: WEBHOOK DE STRIPE (Placeholder)
# Se ha eliminado el webhook del router y se ha incluido como comentario aquí.
# Si estás usando el router, elimina esto. Si no, úsalo como guía.
# ==========================================================
# @app.post("/api/stripe-webhook")
# async def stripe_webhook(request: Request):
#    ... (Implementación real del webhook)
