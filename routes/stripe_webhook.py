from fastapi import APIRouter, HTTPException, Request
import stripe
import os

router = APIRouter(prefix="/stripe", tags=["Stripe"])

# Configura tu clave secreta de Stripe desde variables de entorno
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

@router.post("/create-checkout-session")
async def create_checkout_session(request: Request):
    try:
        data = await request.json()
        # Monto total en centavos (ejemplo: $50.00 → 5000)
        amount = int(data.get("amount", 5000))
        currency = "usd"

        # Crear sesión de checkout en Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": data.get("product_name", "Servicio Ateneo Clínico IA")},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=data.get("success_url", "https://ateneoclinicoia.onrender.com/success"),
            cancel_url=data.get("cancel_url", "https://ateneoclinicoia.onrender.com/cancel"),
        )

        return {"checkout_url": session.url}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
