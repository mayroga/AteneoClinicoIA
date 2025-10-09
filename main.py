from fastapi import FastAPI
from contextlib import asynccontextmanager
# 🆕 Importa CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware 
# Importa los routers...
from routes.auth import router as auth_router
from routes.volunteer import router as volunteer_router
from routes.professional import router as professional_router
from routes.admin import router as admin_router
from database import init_db
from config import APP_NAME

# Contexto de inicio y cierre de la aplicación
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... (Inicialización de DB)
    print("Initializing Database...")
    init_db()
    yield
    print("Application shutdown complete.")

# Inicialización de la app FastAPI
app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# 🆕 Configuración de CORS
origins = [
    "*", # Permite cualquier origen por ahora (para desarrollo). CÁMBIALO para producción.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, etc.)
    allow_headers=["*"], # Permite todos los encabezados
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
