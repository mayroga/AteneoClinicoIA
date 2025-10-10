from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routes import auth, admin, volunteer, professional, stripe_webhook

# Crear las tablas en la base de datos si no existen
Base.metadata.create_all(bind=engine)

# Inicializar la aplicación FastAPI
app = FastAPI(
    title="Ateneo Clínico IA",
    description="Backend para la plataforma Ateneo Clínico IA — integración de profesionales, voluntarios y pacientes con IA médica.",
    version="1.0.0"
)

# Configurar CORS (importante para frontend hospedado en otro dominio o Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # puedes limitarlo a tu dominio en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prefijo global /api para mantener la coherencia con tu frontend
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(volunteer.router, prefix="/api")
app.include_router(professional.router, prefix="/api")
app.include_router(stripe_webhook.router, prefix="/api")

# Ruta raíz simple
@app.get("/")
def home():
    return {"message": "Ateneo Clínico IA — API en línea correctamente 🚀"}

