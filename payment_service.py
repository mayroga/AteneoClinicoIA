import stripe
from config import STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

stripe.api_key = STRIPE_SECRET_KEY

# Crear pago único (ej. voluntario)
def create_one_time_payment(amount_usd: int, currency: str = "usd", email: str = None):
    """
    Crea un pago único con Stripe para voluntarios.
    amount_usd: monto en USD
    email: correo del usuario
    """
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_usd * 100,  # Stripe trabaja en centavos
            currency=currency,
            receipt_email=email,
            metadata={"purpose": "volunteer_case"}
        )
        return payment_intent.client_secret
    except Exception as e:
        print(f"Error al crear pago: {str(e)}")
        return None

# Crear suscripción para profesionales
def create_subscription(customer_email: str, price_id: str):
    """
    Crea una suscripción Stripe para profesionales.
    price_id: ID del plan definido en Stripe
    """
    try:
        customer = stripe.Customer.create(email=customer_email)
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": price_id}],
            expand=["latest_invoice.payment_intent"]
        )
        return subscription
    except Exception as e:
        print(f"Error al crear suscripción: {str(e)}")
        return None

# Verificar webhook de Stripe (opcional)
def verify_webhook(request):
    """
    Verifica la autenticidad de los eventos de Stripe.
    """
    from flask import request as flask_request
    payload = flask_request.data
    sig_header = flask_request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event
    except stripe.error.SignatureVerificationError as e:
        print(f"Webhook no verificado: {str(e)}")
        return None
