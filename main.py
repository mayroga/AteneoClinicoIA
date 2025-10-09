from fastapi import FastAPI
from contextlib import asynccontextmanager
# Importa los routers (asegúrate de que todos tus archivos routes/ existen y tienen una variable 'router')
from routes.auth import router as auth_router
from routes.volunteer import router as volunteer_router
from routes.professional import router as professional_router
from routes.admin import router as admin_router
from database import init_db
from config import APP_NAME

# Contexto de inicio y cierre de la aplicación
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Función que se ejecuta cuando la aplicación se inicia y se cierra.
    Ideal para inicializar recursos como la base de datos.
    """
    # Inicializa la base de datos al inicio
    print("Initializing Database...")
    init_db()
    yield
    # Lógica de limpieza al cerrar (si es necesaria)
    print("Application shutdown complete.")

# Inicialización de la app FastAPI
# ¡ATENCIÓN! Se eliminan los parámetros docs_url y redoc_url para usar las rutas por defecto: /docs y /redoc
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan, # Vincula la función de inicialización de la DB
)

# Incluir routers (agrupaciones de rutas)
app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(volunteer_router, prefix="/volunteer", tags=["Volunteer"])
app.include_router(professional_router, prefix="/professional", tags=["Professional"])
app.include_router(admin_router, prefix="/admin", tags=["Admin"])

# Ruta raíz de prueba
@app.get("/", tags=["Root"])
async def root():
    """Ruta de bienvenida que verifica que la API está funcionando."""
    return {"message": f"Welcome to {APP_NAME} API. Check /docs for documentation."}
