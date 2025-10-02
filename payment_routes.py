from fastapi import APIRouter, Header, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import stripe
from typing import Optional
import json

from config import settings
from database import update_professional_credits, get_professional_profile

# Inicializar Stripe con la clave secreta
stripe.api_key = settings.STRIPE_SECRET_KEY

# Router para manejar las rutas de pago
router = APIRouter(prefix="/api/v1/payment", tags=["Pagos (Stripe)"])

# --- Modelos de Precios de Créditos ---
# Usaríamos precios reales de Stripe en una app de producción, pero aquí definimos un mock.
CREDIT_PACKS = {
    # Ejemplo: 10 Créditos por 500 centavos (5 USD)
    "pack_10_credits": {"amount_cents": 500, "credits": 10, "description": "Paquete de 10 Créditos"},
    # Ejemplo: 25 Créditos por 1000 centavos (10 USD)
    "pack_25_credits": {"amount_cents": 1000, "credits": 25, "description": "Paquete de 25 Créditos"},
}

# --- ENDPOINT 1: CREAR SESIÓN DE PAGO ---
@router.post("/create-checkout-session")
async def create_checkout_session(
    pack_id: str,
    professional_email: str
):
    """
    Crea una nueva sesión de checkout de Stripe para la compra de créditos.
    """
    if pack_id not in CREDIT_PACKS:
        raise HTTPException(status_code=400, detail="ID de paquete de crédito no válido.")

    pack = CREDIT_PACKS[pack_id]
    
    # Usamos la metadata para pasar el email y los créditos, que se usarán en el Webhook
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': pack['description'],
                    },
                    'unit_amount': pack['amount_cents'],
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url="[TU_URL_DE_ÉXITO]?success=true", # Reemplaza con tu URL real
            cancel_url="[TU_URL_DE_FALLO]?canceled=true",  # Reemplaza con tu URL real
            metadata={
                "professional_email": professional_email,
                "credits_to_add": pack['credits']
            }
        )
        return {"id": session.id, "url": session.url}
    except Exception as e:
        print(f"Error al crear sesión de Stripe: {e}")
        raise HTTPException(status_code=500, detail="Error interno al iniciar el pago.")

# --- ENDPOINT 2: WEBHOOK DE STRIPE (CRÍTICO) ---
@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: Optional[str] = Header(None)):
    """
    Recibe eventos de Stripe. Este endpoint es el que actualiza los créditos del profesional
    una vez que el pago ha sido confirmado (evento checkout.session.completed).
    """
    payload = await request.body()
    
    # 1. Verificar la firma del Webhook
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Firma no válida
        print(f"Error Webhook: Carga útil no válida: {e}")
        return JSONResponse(content={"message": "Invalid payload"}, status_code=400)
    except stripe.error.SignatureVerificationError as e:
        # Firma de webhook no válida
        print(f"Error Webhook: Firma no válida: {e}")
        return JSONResponse(content={"message": "Invalid signature"}, status_code=400)
    
    # 2. Manejar el evento confirmado
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Extracción de datos de la metadata que enviamos al crear la sesión
        professional_email = session.metadata.get('professional_email')
        credits_to_add = session.metadata.get('credits_to_add')
        
        print(f"Webhook recibido: Pago exitoso de {professional_email} para {credits_to_add} créditos.")
        
        if professional_email and credits_to_add:
            try:
                credits_amount = int(credits_to_add)
                
                # CRÍTICO: Actualizar los créditos en la base de datos
                new_credits = update_professional_credits(professional_email, credits_amount)
                
                if new_credits is not None:
                    print(f"ÉXITO: {credits_amount} créditos añadidos a {professional_email}. Total: {new_credits}")
                else:
                    # Esto podría indicar que el profesional no existe en la DB
                    print(f"ADVERTENCIA: No se pudo actualizar créditos para {professional_email}. El perfil no existe.")
                    
            except ValueError:
                print(f"ERROR Webhook: 'credits_to_add' no es un entero válido: {credits_to_add}")
            except Exception as e:
                print(f"ERROR Webhook: Fallo al actualizar DB: {e}")

    # Retorno estándar 200 para Stripe para indicar que el evento fue recibido
    return JSONResponse(content={"status": "success"}, status_code=200)
