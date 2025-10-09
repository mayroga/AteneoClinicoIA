import os
import stripe
from config import STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

stripe.api_key = STRIPE_SECRET_KEY

# -----------------------------
# Crear sesión de pago para voluntarios
# -----------------------------
def create_volunteer_payment_session(user_email: str, case_price: int = 50):
    """
    Crea una sesión de pago de Stripe para voluntarios
    """
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'Caso Clínico Voluntario'},
                    'unit_amount': case_price * 100,  # Stripe trabaja en centavos
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://yourwebsite.com/payment-success',
            cancel_url='https://yourwebsite.com/payment-cancel',
            customer_email=user_email
        )
        return {"id": session.id, "url": session.url}
    except Exception as e:
        return {"error": str(e)}

# -----------------------------
# Crear suscripción para profesionales
# -----------------------------
def create_professional_subscription(customer_email: str, price_id: str):
    """
    Crea una suscripción de Stripe para profesionales según su nivel
    price_id: ID del plan en Stripe (Level 1, 2 o 3)
    """
    try:
        # Crear cliente si no existe
        customer = stripe.Customer.create(email=customer_email)
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{'price': price_id}],
            expand=['latest_invoice.payment_intent'],
        )
        return subscription
    except Exception as e:
        return {"error": str(e)}

# -----------------------------
# Verificar webhook de Stripe
# -----------------------------
def verify_webhook_signature(payload: bytes, sig_header: str):
    """
    Verifica la firma de Stripe para seguridad de webhooks
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        # Payload inválido
        return {"error": f"Invalid payload: {str(e)}"}
    except stripe.error.SignatureVerificationError as e:
        # Firma inválida
        return {"error": f"Invalid signature: {str(e)}"}

# -----------------------------
# Manejar eventos de pago exitoso
# -----------------------------
def handle_payment_success(event):
    """
    Lógica cuando el pago de voluntario o profesional es exitoso
    """
    # Puedes personalizar según tipo de evento
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_email')
        # Aquí se podría activar el caso clínico del voluntario o la suscripción del profesional
        return {"status": "success", "email": customer_email}
    return {"status": "ignored"}
