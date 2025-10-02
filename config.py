from pydantic_settings import BaseSettings
from pydantic import Field
import os
from typing import Optional

# Carga variables de entorno desde un archivo .env si existe (útil para desarrollo local)
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseSettings):
    """
    Configuración de la aplicación que carga las variables de entorno.
    Incluye precios segmentados por tipo de usuario y acceso de bypass.
    """
    
    # --- Configuración del Servidor y URL Propio ---
    app_base_url: str = Field(
        default="https://ateneoclinicoia.onrender.com", 
        description="El URL base de la aplicación para enlaces."
    )
    
    # --- Precios por Tipo de Usuario (NUEVO) ---
    # Voluntarios: $40.00 (Dentro del rango $30-$50)
    price_volunteer: float = Field(
        default=40.00,
        description="Precio de suscripción para Voluntarios (Ejemplo: $40.00)."
    )
    # Profesionales: $149.99 (Por encima de $120)
    price_professional: float = Field(
        default=149.99,
        description="Precio de suscripción para Profesionales (Ejemplo: $149.99)."
    )
    
    # --- Claves Secretas para Servicios Externos ---

    # Clave de API para Google GenAI (Gemini)
    google_api_key: str = Field(
        default="", 
        description="Clave de API para el servicio de Google Gemini."
    )
    
    # Clave de API para SendGrid
    sendgrid_api_key: str = Field(
        default="",
        description="Clave de API para el envío de correos electrónicos con SendGrid."
    )
    
    # Configuración de la Base de Datos (PostgreSQL)
    database_url: str = Field(
        default="",
        description="URL de conexión completo para la base de datos PostgreSQL."
    )

    # CLAVE DE BYPASS: Lee la variable de entorno ADMIN_BYPASS_KEY
    admin_bypass_key: str = Field(
        default="", 
        description="Clave de acceso de administrador para exención de pago y privilegios."
    )

    # Email del remitente
    default_sender_email: str = Field(
        default="no-responder@ateneoclinicoia.com",
        description="Dirección de correo electrónico del remitente por defecto."
    )

    class Config:
        env_file = ".env"
        env_prefix = ''
        extra = "ignore" 

settings = Settings()
