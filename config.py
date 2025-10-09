import os

# Variables de entorno críticas
# Estas DEBEN ser definidas en Render para que la aplicación inicie sin "Timed Out"
DATABASE_URL = os.getenv("DATABASE_URL")
EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
ADMIN_BYPASS_KEY = os.getenv("ADMIN_BYPASS_KEY")

# Configuraciones generales
APP_NAME = "Ateneo Clínico IA"
APP_ENV = os.getenv("APP_ENV", "production")
DEBUG = os.getenv("DEBUG", "False") == "True"

# Seguridad
# IMPORTANTE: El valor predeterminado SÓLO se usa si no está en Render.
# Ya que lo añadiste en Render, se usará ese valor seguro.
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey_change_me")

# Configuración de correo
EMAIL_SENDER = SENDER_EMAIL
EMAIL_SUBJECT_PREFIX = "[Ateneo Clínico IA]"

# Configuración de IA
AI_TIMEOUT_SECONDS = 7  # Tiempo máximo de respuesta de la IA
AI_MODEL = "gemini"     # Modelo de IA principal (gemini-2.5-flash-preview-05-20 se usaría para la implementación)

# Stripe
STRIPE_CURRENCY = "usd"
