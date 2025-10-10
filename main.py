from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

# Importa las dependencias necesarias
from routes.auth import router as auth_router
from routes.volunteer import router as volunteer_router
from routes.professional import router as professional_router
from routes.admin import router as admin_router
# Importación del ROUTER DE STRIPE WEBHOOK
from routes.stripe_webhook import router as stripe_webhook_router
# Inicialización de DB
from database import init_db
from config import APP_NAME


# ==============================================================
# CONTEXTO DE INICIO Y CIERRE DE LA APLICACIÓN
# ==============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función que se ejecuta cuando la aplicación se inicia para preparar la base de datos.
    """
    print("Initializing Database...")
    init_db()
    yield
    print("Application shutdown complete.")


# ==============================================================
# INICIALIZACIÓN DE LA APP FASTAPI
# ==============================================================
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)


# ==============================================================
# CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS
# ==============================================================
app.mount("/static", StaticFiles(directory="static"), name="static")


# ==============================================================
# CONFIGURACIÓN DE CORS
# ==============================================================
origins = [
    "https://ateneoclinicoia.onrender.com",
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================
# RUTA RAÍZ: SIRVE EL ARCHIVO HTML PRINCIPAL
# ==============================================================
@app.get("/", tags=["Root"], response_class=HTMLResponse)
async def serve_frontend():
    """Sirve el archivo HTML principal de la aplicación para el frontend."""
    html_file_path = "index.html"
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
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
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/api/volunteer", tags=["Volunteer"])
app.include_router(professional_router, prefix="/api/professional", tags=["Professional"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(stripe_webhook_router, prefix="/api")  # Webhook de Stripe queda en /api/stripe/webhook


# ==============================================================
# MENSAJE DE PRUEBA
# ==============================================================
@app.get("/api", tags=["Status"])
async def status_check():
    return {"message": "✅ API Ateneo Clínico IA en línea y funcionando correctamente"}
