from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/payment", tags=["Payment"])

# ==============================
# PAYMENT LINKS DEL ATENEO CLÍNICO IA (REALES)
# ==============================
PAYMENT_LINKS = {
    "Nivel1": "https://buy.stripe.com/28EfZggMDbq35kPg9Z7Vm07",          # Diagnóstico Rápido - $10
    "Nivel2": "https://buy.stripe.com/dRm7sKbsjdyb7sX7Dt7Vm08",          # Evaluación Estándar - $50
    "Nivel3": "https://buy.stripe.com/5kQ14m8g78dR4gL5vl7Vm09",          # Planificación y Protocolo - $100
    "Nivel4": "https://buy.stripe.com/6oUcN43ZReCf9B53nd7Vm0a",          # Debate y Evidencia - $200
    "Nivel5": "https://buy.stripe.com/cNibJ0cwn1PtfZt6zp7Vm0b",          # Mesa Clínica Premium - $500
    "AddonImagen": "https://buy.stripe.com/6oU3cu7c3gKn6oT4rh7Vm0c",     # Análisis de Imagen/Laboratorio - $10
    "AddonAudio": "https://buy.stripe.com/eVqdR87c3dybbJd5vl7Vm0d",      # Audio Profesional (TTS) - $3
}

# ==============================
# ENDPOINT PARA OBTENER LINK
# ==============================
@router.post("/get-link")
async def get_payment_link(request: Request):
    data = await request.json()
    nivel = data.get("nivel")  # Debe venir del frontend
    if not nivel or nivel not in PAYMENT_LINKS:
        raise HTTPException(status_code=400, detail="Nivel o add-on inválido")
    return {"payment_url": PAYMENT_LINKS[nivel]}
