from pydantic_settings import BaseSettings
from pydantic import Field
import os

# Carga variables de entorno desde un archivo .env si existe (útil para desarrollo local)
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseSettings):
    """
    Configuración de la aplicación que carga las variables de entorno.
    Se busca la variable ADMIN_BYPASS_KEY para el acceso de administrador.
    """
    
    # --- Configuración del Servidor y URL Propio ---
    app_base_url: str = Field(
        default="https://ateneoclinicoia.onrender.com", 
        description="El URL base de la aplicación para enlaces."
    )
    
    # --- Claves Secretas para Servicios Externos ---

    # Clave de API para Google GenAI (Gemini)
    google_api_key: str = Field(
        ..., # Requerido
        description="Clave de API para el servicio de Google Gemini."
    )
    
    # Clave de API para SendGrid
    sendgrid_api_key: str = Field(
        ..., # Requerido
        description="Clave de API para el envío de correos electrónicos con SendGrid."
    )
    
    # Configuración de la Base de Datos (PostgreSQL)
    database_url: str = Field(
        ...,
        description="URL de conexión completo para la base de datos PostgreSQL."
    )

    # CLAVE DE BYPASS: Lee la variable de entorno ADMIN_BYPASS_KEY
    admin_bypass_key: str = Field(
        default="", 
        description="Clave de acceso de administrador para exención de pago y privilegios."
    )

    # Puedes agregar otras configuraciones como el email del remitente
    default_sender_email: str = Field(
        default="no-responder@ateneoclinicoia.com",
        description="Dirección de correo electrónico del remitente por defecto."
    )

    class Config:
        env_file = ".env"
        env_prefix = '' # Prefijo vacío para leer nombres exactos (ej: ADMIN_BYPASS_KEY)
        extra = "ignore" 

settings = Settings()
