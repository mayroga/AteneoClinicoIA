from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
from database import Base, engine # Importamos Base y engine para crear tablas
from routes import auth, volunteer, professional, admin

# 1. Definición de la aplicación y manejo de eventos (FastAPI)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lógica de inicio de la aplicación: Crear tablas DB
    # Este paso reemplaza la llamada Flask init_db(app)
    print("Iniciando aplicación y creando tablas de base de datos...")
    Base.metadata.create_all(bind=engine)
    yield
    # Lógica de apagado (opcional)
    print("Apagando aplicación...")

# Inicialización de la app FastAPI
app = FastAPI(
    title="Ateneo Clínico IA", 
    version="1.0.0",
    lifespan=lifespan
)

# 2. Registrar Routers (FastAPI)
# Usamos .router, que es el nombre de la variable definida en tus archivos de ruta (e.g., routes/volunteer.py)
app.include_router(auth.router, prefix='/auth', tags=["Auth"])
app.include_router(volunteer.router, prefix='/volunteer', tags=["Volunteer"])
app.include_router(professional.router, prefix='/professional', tags=["Professional"])
app.include_router(admin.router, prefix='/admin', tags=["Admin"])

# 3. La ruta raíz (simplemente devuelve un mensaje)
@app.get('/')
def index():
    return {"message": "Bienvenido al Ateneo Clínico IA (API en funcionamiento)"}

# 4. Error handlers sencillos (FastAPI maneja 404s por defecto)

# NOTA: El if __name__ == '__main__': es eliminado. 
# La aplicación será iniciada por Gunicorn/Uvicorn usando el Start Command: gunicorn main:app
