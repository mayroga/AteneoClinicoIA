from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # Claves de Servicio
    google_api_key: str = Field(default="", description="Clave API de Google para el modelo Gemini.")
    sendgrid_api_key: str = Field(default="", description="Clave API de SendGrid para el envío de correos.")
    database_url: str = Field(default="", description="URL de conexión a la base de datos PostgreSQL.")
    
    # NUEVA CLAVE: Clave Secreta de Stripe para cobros.
    stripe_secret_key: str = Field(default="", description="Clave Secreta de Stripe para procesar pagos.")

    # URL de la Aplicación
    app_base_url: str = Field("https://ateneoclinicoia.onrender.com", description="URL base de la aplicación para enlaces.")

    # Configuración de Acceso y Precios
    admin_bypass_key: str = Field(default="", description="Clave secreta para el acceso ilimitado del desarrollador (ID de usuario).")
    
    # Precios Segmentados por Rol
    price_volunteer: float = Field(40.00, description="Precio de la suscripción para Voluntarios (USD).")
    price_professional: float = Field(149.99, description="Precio de la suscripción para Profesionales (USD).")
    
    # Configuración de Correo
    default_sender_email: str = Field("noreply@ateneoclinicoia.com", description="Correo electrónico del remitente por defecto.")

    model_config = SettingsConfigDict(
        env_file='.env', 
        env_file_encoding='utf-8', 
        extra='allow'
    )

settings = Settings()
