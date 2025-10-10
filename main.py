from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
# Importación necesaria para forzar la renderización de la documentación
from fastapi.openapi.docs import get_redoc_html

# Importa tus routers (asegúrate de que las rutas a los archivos sean correctas)
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

# Configuración de CORS (Cross-Origin Resource Sharing)
origins = [
    # ✅ ESTO ES LO QUE ESTAMOS CORRIGIENDO: Usamos el dominio específico en lugar de "*"
    "https://ateneoclinicoia.onrender.com", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"],  # Permite todos los encabezados
)


# <<--- SOLUCIÓN: RUTA PERSONALIZADA PARA REDOC --- >>
# Usamos Redoc por ser más estable en entornos de hosting complejos
@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    """
    Sirve la página HTML de Redoc. Esto fuerza al navegador a renderizar
    la interfaz interactiva en lugar del JSON.
    """
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Redoc"
    )

# <<--- RUTA PARA EL openapi.json QUE USA LA DOCUMENTACIÓN --- >>
# Mantenemos esta sin cambios, es el corazón de la documentación.
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
