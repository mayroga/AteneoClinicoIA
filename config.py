from pydantic import Field, EmailStr
from pydantic_settings import BaseSettings

# NOTA IMPORTANTE: Esta clase define las variables de entorno (secrets) que tu 
# aplicación FastAPI necesita. Pydantic-Settings las cargará automáticamente 
# desde el entorno de Render o variables locales.

class Settings(BaseSettings):
    """
    Configuración de la aplicación cargada desde variables de entorno.
    """
    
    # --- Configuración Base ---
    # La URL de la base de datos PostgreSQL, esencial para Render.
    database_url: str = Field(..., alias="DATABASE_URL", description="URL de conexión a PostgreSQL.")

    # La URL base de la aplicación (usada para redirecciones de Stripe y enlaces virales).
    app_base_url: str = Field("http://localhost:8000", description="URL base de la app para webhooks/redirecciones.")

    # --- Servicios de IA (Google GenAI) ---
    google_api_key: str = Field(..., alias="GOOGLE_API_KEY", description="Clave API de Google GenAI.")

    # --- Servicios de Pago (Stripe) ---
    stripe_secret_key: str = Field(..., alias="STRIPE_SECRET_KEY", description="Clave secreta de Stripe.")
    # Clave necesaria para verificar la autenticidad de los eventos de webhook de Stripe.
    stripe_webhook_secret: str = Field(..., alias="STRIPE_WEBHOOK_SECRET", description="Clave secreta del webhook de Stripe.")

    # Precios de los servicios (en USD)
    price_volunteer: float = Field(15.00, description="Precio de la cuota de Voluntario.")
    price_professional: float = Field(25.00, description="Precio de la cuota de Profesional (Crédito).")
    
    # Clave de bypass para el desarrollador (debe ser secreta)
    admin_bypass_key: str = Field("", alias="ADMIN_BYPASS_KEY", description="Clave de ID de usuario para acceso gratuito ilimitado.")

    # --- Servicios de Correo (SendGrid) ---
    sendgrid_api_key: str = Field(..., alias="SENDGRID_API_KEY", description="Clave API de SendGrid.")
    default_sender_email: EmailStr = Field(..., alias="DEFAULT_SENDER_EMAIL", description="Email del remitente para SendGrid.")

    # Se puede omitir 'Config' en Pydantic v2 si solo se usa BaseSettings 
    # y se confía en la carga automática del entorno.
    pass

# Instancia de configuración que se importa en main.py
settings = Settings()
