import os
from dotenv import load_dotenv

# Solo para desarrollo local, ignorado en Render si la variable existe.
load_dotenv() 

class Settings:
    # Claves de la API (Cargadas de Render de forma segura)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "FAKE_GEMINI_KEY")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "sk_FAKE_STRIPE_KEY")
    
    # TU CLAVE DE ACCESO ILIMITADO
    ADMIN_BYPASS_KEY: str = os.getenv("ADMIN_BYPASS_KEY", "PON_TU_CLAVE_MAESTRA_LARGA_AQUI")
    
    # Configuración de la Base de Datos
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/ateneo_db")

    # Seguridad y CORS
    SECRET_KEY: str = os.getenv("SECRET_KEY", "a_super_secret_and_long_random_key_for_jwt")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

settings = Settings()
