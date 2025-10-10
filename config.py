import os
from dotenv import load_dotenv

load_dotenv() 

# =================================================================
# CONFIGURACIONES BÁSICAS
# =================================================================
APP_NAME = os.getenv("APP_NAME", "Ateneo Clínico IA")
DATABASE_URL = os.getenv("DATABASE_URL")

# =================================================================
# CLAVES DE SERVICIO
# =================================================================
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")

# Stripe (Asumimos que estas están en Render)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# URL de la aplicación (CRUCIAL para los redireccionamientos de Stripe)
# Lee la variable que definiste en Render, con un respaldo local.
RENDER_APP_URL = os.getenv("RENDER_APP_URL", "http://localhost:8000")

# Otros ajustes (ej. timeout para llamadas a IA)
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", 60)) # Aumentado a 60s
