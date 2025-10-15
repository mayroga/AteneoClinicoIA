import os
import stripe
from dotenv import load_dotenv

load_dotenv()

# Claves Esenciales
ADMIN_BYPASS_KEY = os.environ.get("ADMIN_BYPASS_KEY", "default_dev_key")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# URL Base de tu aplicación en Render (CRÍTICO para redirecciones de Stripe)
# DEBES establecer esta variable en tu entorno de Render
BASE_URL = os.environ.get("URL_SITE", "https://ateneoclinicoia.onrender.com")

# Inicialización global de Stripe (CRÍTICO)
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    print("❌ ERROR: STRIPE_SECRET_KEY no configurada. Los pagos fallarán.")

# Puedes inicializar el cliente Gemini aquí
# from google import genai
# client = genai.Client(api_key=GEMINI_API_KEY)
