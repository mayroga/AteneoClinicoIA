from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles 
import os

# Importa tus routers
from routes.auth import router as auth_router
from routes.volunteer import router as volunteer_router
from routes.professional import router as professional_router
from routes.admin import router as admin_router
# IMPORTACIÓN CRÍTICA DEL WEBHOOK
from routes.stripe_webhook import router as stripe_webhook_router
# Inicialización de DB
from database import init_db
from config import APP_NAME

# Contexto de inicio y cierre de la aplicación
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    init_db()
    yield
    print("Application shutdown complete.")

# Inicialización de la app FastAPI
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)

# CONFIGURACIÓN DE ARCHIVOS ESTÁTICOS
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuración de CORS
origins = [
    "https://ateneoclinicoia.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RUTA RAÍZ CORREGIDA: SIRVE EL ARCHIVO HTML
@app.get("/", tags=["Root"], response_class=HTMLResponse)
async def serve_frontend():
    html_file_path = "index.html" 
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Error: Archivo index.html no encontrado.</h1>", status_code=500)


# RUTAS DE DOCUMENTACIÓN
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
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

# INCLUSIÓN DE ROUTERS
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/volunteer", tags=["Volunteer"])
app.include_router(professional_router, prefix="/professional", tags=["Professional"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])
# INCLUSIÓN DEL WEBHOOK
app.include_router(stripe_webhook_router) # Notar que este no lleva prefix para que la ruta sea /stripe/webhook
