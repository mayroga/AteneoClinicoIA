from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
# Importación necesaria para forzar la renderización de la documentación
from fastapi.openapi.docs import get_redoc_html

# =================================================================
# 1. IMPORTACIÓN AÑADIDA PARA ARCHIVOS ESTÁTICOS
from fastapi.staticfiles import StaticFiles 
# =================================================================

# Importa tus routers
from routes.auth import router as auth_router
from routes.volunteer import router as volunteer_router
from routes.professional import router as professional_router
from routes.admin import router as admin_router
from database import init_db
from config import APP_NAME

# Contexto de inicio y cierre de la aplicación para inicializar la base de datos
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función que se ejecuta cuando la aplicación se inicia para preparar recursos
    como la conexión a la base de datos.
    """
    print("Initializing Database...")
    init_db()
    yield
    # Lógica de limpieza al cerrar (si es necesaria)
    print("Application shutdown complete.")

# Inicialización de la app FastAPI
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    # Desactivamos ambas rutas por defecto para forzar Redoc manualmente
    docs_url=None,  
    redoc_url=None  
)

# =================================================================
# 2. CONFIGURACIÓN AÑADIDA PARA ARCHIVOS ESTÁTICOS
# =================================================================
# Esto mapea la carpeta 'static' del proyecto al path URL '/static', 
# permitiendo que el navegador cargue tus recursos.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configuración de CORS (Cross-Origin Resource Sharing)
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


# <<--- SOLUCIÓN: RUTA PERSONALIZADA PARA REDOC --- >>
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """
    Sirve la página HTML de Redoc.
    """
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Redoc"
    )

# <<--- RUTA PARA EL openapi.json QUE USA LA DOCUMENTACIÓN --- >>
@app.get(app.openapi_url, include_in_schema=False)
async def get_open_api_endpoint():
    from fastapi.openapi.utils import get_openapi
    return get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

# Incluir routers (agrupaciones de rutas de tu API)
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/volunteer", tags=["Volunteer"])
app.include_router(professional_router, prefix="/professional", tags=["Professional"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Ruta raíz de prueba
@app.get("/", tags=["Root"])
async def root():
    """Ruta de bienvenida que verifica que la API está funcionando."""
    return {"message": f"Welcome to {APP_NAME} API. Check /redoc for documentation."}
