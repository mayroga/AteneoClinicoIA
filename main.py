import os
import stripe
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session 

# --- IMPORTS DE MÓDULOS DEL PROYECTO ---
# Importaciones de configuración: Claves y URLs
from config import (
    APP_NAME, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, 
    GEMINI_API_KEY, ADMIN_BYPASS_KEY, RENDER_APP_URL
)
# Importaciones de base de datos y modelos
from database import init_db, SessionLocal, get_case_by_id
import models 
# Importaciones de routers
from routes.auth import router as auth_router 
from routes.volunteer import router as volunteer_router
from routes.developer import router as developer_router 

# --- Dummies (Manteniendo la estructura de carpetas) ---
from fastapi import APIRouter
admin_router = APIRouter()
professional_router = APIRouter()
# -----------------------------------------------

# 💡 Cliente Gemini
import google.generativeai as genai # Asumiendo que es la importación correcta

# --- Inicialización de Clientes y Variables ---
GEMINI_MODEL = "gemini-2.5-flash" 

# Inicialización de Stripe
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ==============================================================
# CONFIGURACIÓN DE CLIENTE GEMINI (CORREGIDO)
# ==============================================================
gemini_client = None
if GEMINI_API_KEY:
    try:
        # 1. Configurar la clave API globalmente (obligatorio para el SDK de Gemini)
        genai.configure(api_key=GEMINI_API_KEY)
        
        # 2. Inicializar el cliente sin pasar la clave por segunda vez
        gemini_client = genai.Client() 
        print("Cliente Gemini inicializado exitosamente.")
    except Exception as e:
        # El error original 'has no attribute Client' se lanzó aquí.
        # Al usar configure/Client() en dos pasos, debería resolverse.
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
    """Función que se ejecuta cuando la aplicación se inicia para preparar la base de datos."""
    print("Initializing Database...")
    init_db() # Llama a la inicialización de DB (crea tablas)
    yield
    print("Application shutdown complete.")


# ==============================================================
# INICIALIZACIÓN ÚNICA DE LA APP FASTAPI
# ==============================================================
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None, # Desactivar docs en prod por defecto, si es necesario
    redoc_url=None # Desactivar redoc en prod por defecto, si es necesario
)

# ==============================================================
# CONFIGURACIÓN DE CORS
# ==============================================================
origins = [
    RENDER_APP_URL,
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*", # Dejar el wildcard si es necesario para el desarrollo de frontend
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================
# CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS Y RUTA RAÍZ
# ==============================================================
# 💡 AJUSTE: Montamos el directorio 'static' para servir CSS/JS/Imágenes del frontend.
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", tags=["Root"], response_class=HTMLResponse)
async def serve_frontend():
    """Ruta para servir la página principal del frontend (index.html)."""
    html_file_path = "index.html"
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Error: Archivo index.html no encontrado.</h1>",
            status_code=500
        )


# ==============================================================
# INCLUSIÓN DE ROUTERS CON PREFIJO GLOBAL /api
# ==============================================================
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/api", tags=["Volunteer"]) 
app.include_router(professional_router, prefix="/api", tags=["Professional"]) 
app.include_router(developer_router, prefix="/api", tags=["Developer/Admin"]) 
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])


@app.get("/api", tags=["Status"])
async def status_check():
    """Mensaje de prueba para verificar que la API está en línea."""
    return {"message": "✅ API Ateneo Clínico IA en línea y funcionando correctamente"}


# ==========================================================
# WEBHOOK DE STRIPE (/api/stripe-webhook) - IMPLEMENTACIÓN FINAL
# ==========================================================
@app.post("/api/stripe-webhook")
async def stripe_webhook(request: Request):
    """
    Maneja los eventos del Webhook de Stripe. Si el pago es exitoso, 
    llama a la IA para el análisis y guarda el resultado en la DB.
    """
    
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Clave secreta del Webhook no configurada.")

    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        print(f"Error de firma de Webhook: {e}")
        raise HTTPException(status_code=400, detail="Firma de Webhook no válida")
    except stripe.error.SignatureVerificationError as e:
        print(f"Error de verificación de firma de Stripe: {e}")
        raise HTTPException(status_code=400, detail="Fallo en la verificación de firma de Stripe")
    
    # ------------------------------------------------------
    # --- PROCESAMIENTO DE EVENTO CRÍTICO: PAGO EXITOSO ---
    # ------------------------------------------------------
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Obtener los metadatos del caso que guardamos al crear la sesión
        case_id = session.metadata.get('case_id')
        case_description = session.metadata.get('case_description')
        
        if not case_id or not case_description:
            print("Error: Metadatos de caso incompletos en la sesión de Stripe.")
            return {"status": "error", "message": "Metadatos incompletos"}

        db_session: Session = SessionLocal()
        try:
            case = get_case_by_id(db_session, int(case_id))
            
            if not case:
                print(f"Advertencia: Caso ID {case_id} no encontrado en la DB.")
                return {"status": "error", "message": "Caso no encontrado"}

            if case.status != 'pending_payment':
                 print(f"Advertencia: Caso ID {case_id} ya fue procesado.")
                 return {"status": "ignored", "message": "Caso ya procesado"}

            # 1. Marcar como pagado
            case.status = 'paid'
            db_session.commit()
            
            # 2. Llamar a Gemini para el análisis (el servicio principal)
            analysis_result = "Análisis pendiente: Cliente Gemini no inicializado al momento del webhook."
            if gemini_client:
                prompt_ia = (
                    f"Genera un análisis profesional detallado del caso clínico proporcionado, incluyendo "
                    f"un resumen, un diagnóstico diferencial, y un plan de manejo completo. Caso: {case_description}"
                )
                
                ia_response = gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt_ia
                )
                analysis_result = ia_response.text

            # 3. Guardar el resultado del análisis y marcar como completado
            case.analysis_result = analysis_result
            case.status = 'analysis_complete'
            case.completed_at = datetime.datetime.utcnow()
            case.stripe_session_id = session.id 
            db_session.commit()

            print(f"✅ Caso ID {case_id} procesado y análisis guardado en DB.")
            return {"status": "success", "received": True}

        except Exception as e:
            db_session.rollback()
            print(f"ERROR FATAL en el Webhook de Stripe al procesar el caso {case_id}: {e}")
            # Aunque haya un error interno, devolvemos 200 a Stripe para evitar reintentos infinitos
            return {"status": "error", "message": f"Error interno: {e}"}
        finally:
            db_session.close()
    
    # Ignorar otros eventos de Stripe
    return {"status": "ignored", "message": "Evento de Stripe ignorado."}
