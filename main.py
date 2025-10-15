from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Inicialización de la aplicación FastAPI
app = FastAPI(title="Ateneo Clínico IA Backend API")

# =========================================================================
# 1. CONFIGURACIÓN CRÍTICA DE CORS
# Esto permite que el frontend (HTML) se comunique con el backend (FastAPI)
# cuando están en diferentes dominios (como local y Render).
# Nota: En producción, es mejor especificar dominios en lugar de usar "*".
# =========================================================================

origins = [
    "*",  # Permite todos los orígenes para facilitar las pruebas
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    """Ruta de prueba simple para verificar que la API está funcionando."""
    return {"message": "Ateneo Clínico IA API está funcionando. ¡Conexión OK!"}

# =========================================================================
# 2. ENDPOINT PARA VOLUNTARIOS (Análisis de Caso) - Precio: $50 USD
# RUTA: /volunteer/create-case
# =========================================================================

@app.post("/volunteer/create-case")
async def create_volunteer_case(
    user_id: int = Form(...),
    description: str = Form(...),
    has_legal_consent: bool = Form(...),
    developer_bypass_key: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    Simula el proceso de creación de un caso por parte de un voluntario.
    Requiere un pago o una clave de bypass.
    """
    
    # 1. Lógica de Bypass (Para desarrolladores)
    if developer_bypass_key == "DEBUG_VOLUNTEER":
        file_name = file.filename if file else "No se adjuntó archivo"
        
        # En un entorno real, aquí se procesaría el caso con la IA
        return {
            "status": "success",
            "message": "Bypass de pago activado. Caso de voluntario procesado.",
            "data": {
                "user_id": user_id,
                "description_length": len(description),
                "file_uploaded": file_name,
                "consent_given": has_legal_consent
            }
        }

    # 2. Lógica de Pago (Simulación de Stripe)
    
    # Nota CRÍTICA: La URL devuelta al frontend DEBE contener 'payment_url'
    # para que la lógica de redirección del HTML se active.
    
    return {
        "status": "payment_required",
        "payment_url": "https://simulacion.stripe.com/checkout/volunteer_50usd",
        "price": 50,
        "currency": "USD"
    }

# =========================================================================
# 3. ENDPOINT PARA PROFESIONALES (Activación de Herramienta) - Precio: $100 USD
# RUTA: /professional/activate-tool
# =========================================================================

@app.post("/professional/activate-tool")
async def activate_professional_tool(
    user_id: int = Form(...),
    tool_name: str = Form(...),
    developer_bypass_key: Optional[str] = Form(None)
):
    """
    Simula la activación de una herramienta avanzada por parte de un profesional.
    Requiere un pago o una clave de bypass.
    """
    
    # 1. Lógica de Bypass (Para desarrolladores)
    if developer_bypass_key == "DEBUG_PROFESSIONAL":
        
        # En un entorno real, aquí se desbloquearía el acceso a la herramienta
        return {
            "status": "success",
            "message": f"Bypass de pago activado. Herramienta '{tool_name}' desbloqueada.",
            "access_token": "TOKEN_DE_ACCESO_PROFESIONAL_GENERADO"
        }

    # 2. Lógica de Pago (Simulación de Stripe)
    
    # Nota CRÍTICA: La URL devuelta al frontend DEBE contener 'payment_url'
    # para que la lógica de redirección del HTML se active.
    
    return {
        "status": "payment_required",
        "payment_url": "https://simulacion.stripe.com/checkout/professional_100usd",
        "price": 100,
        "currency": "USD"
    }

# Para correr este archivo localmente, puedes usar:
# uvicorn main:app --reload
