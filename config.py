from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, Field
import os

class Settings(BaseSettings):
    """
    Define todas las variables de entorno requeridas para la aplicación.
    Los nombres aquí deben coincidir exactamente con las variables de entorno de tu servidor.
    """
    
    # Base de Datos
    DATABASE_URL: str
    
    # Servicios de IA
    GEMINI_API_KEY: str

    # Servicios de Correo (SendGrid)
    EMAIL_API_KEY: str # Corresponde a tu código secreto de SendGrid
    SENDER_EMAIL: EmailStr # Corresponde al email desde donde se envían las notificaciones
    
    # Servicios de Pago (Stripe)
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    # Clave de Bypass Administrativo (Acceso gratis/ilimitado)
    ADMIN_BYPASS_KEY: str = Field(..., default='MICHA991775')


    # Metadata de la configuración para pydantic-settings
    model_config = SettingsConfigDict(
        env_file=".env",
        extra='ignore'
    )

# Instancia única de la configuración para uso global
settings = Settings()
