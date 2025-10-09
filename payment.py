import stripe
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
from config import STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

stripe.api_key = STRIPE_SECRET_KEY
router = APIRouter()

# Crear sesión de pago para voluntarios
@router.post("/create-payment-volunteer")
async def create_payment_volunteer(amount: int, email: str):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Caso Clínico Voluntario"},
                    "unit_amount": amount * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://tusitio.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://tusitio.com/cancel",
            customer_email=email,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Crear sesión de pago para profesionales
@router.post("/create-payment-professional")
async def create_payment_professional(amount: int, email: str):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Suscripción Profesional Ateneo Clínico"},
                    "unit_amount": amount * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://tusitio.com/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://tusitio.com/cancel",
            customer_email=email,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Webhook para recibir confirmación de pago
@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "Payload inválido"})
    except stripe.error.SignatureVerificationError:
        return JSONResponse(status_code=400, content={"message": "Firma inválida"})

    # Manejo de eventos relevantes
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Aquí se puede actualizar la base de datos con pago confirmado
        print(f"Pago completado para: {session['customer_email']}, amount: {session['amount_total']}")

    return JSONResponse(status_code=200, content={"message": "Webhook recibido"})
