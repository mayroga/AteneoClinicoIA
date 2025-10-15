from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routes import volunteer, professional, admin # Importar routers

# Crear tablas (si no existen)
try:
    Base.metadata.create_all(bind=engine)
    print("Inicialización de base de datos exitosa.")
except Exception as e:
    print(f"Error al inicializar la DB: {e}")

app = FastAPI(
    title="Ateneo Clínico IA API",
    description="Servicio de IA con control de acceso por pago y bypass de desarrollador."
)

# Configuración CORS
origins = [
    "*", 
    # Añade tus dominios de frontend aquí para seguridad
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enlazar todos los routers
app.include_router(volunteer.router, prefix="")
app.include_router(professional.router, prefix="")
app.include_router(admin.router, prefix="")

@app.get("/")
def read_root():
    return {"message": "Ateneo Clínico IA API funcionando correctamente."}
