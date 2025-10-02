import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Clase que maneja todas las configuraciones de la aplicación, cargadas de variables de entorno (Render).
    """
    
    # --- Configuración de la Aplicación y Seguridad ---
    ADMIN_BYPASS_KEY: str = os.getenv("ADMIN_BYPASS_KEY", "CLAVE_MAESTRA_SECRETA_DEV")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000") # URL del frontend para CORS
    
    # --- Claves de la API (Monetización, IA y Correo) ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "FAKE_GEMINI_KEY")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "sk_FAKE_STRIPE_KEY") # Clave secreta de Stripe para pagos
    EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "TU_CLAVE_API_DE_SENDGRID") # Clave de SendGrid
    SENDER_EMAIL: str = os.getenv("SENDER_EMAIL", "tu.email.verificado@dominio.com") # Email verificado de SendGrid
    
    # --- Configuración de la Base de Datos PostgreSQL (Render) ---
    DB_NAME: str = os.getenv("DB_NAME", "ateneo_db")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")

settings = Settings()
