import stripe
from config import settings
from models import CreatePaymentIntent

# Configura Stripe con tu clave secreta
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_payment_intent(data: CreatePaymentIntent):
    """
    Crea un Payment Intent con Stripe.
    Esto permite a la pasarela de pago manejar la complejidad de la transacción.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=data.amount,
            currency=data.currency,
            payment_method_types=[data.payment_method_type],
            description=data.description,
            receipt_email=data.customer_email,
            metadata={'product': data.description}
        )
        return intent
    except Exception as e:
        print(f"ERROR de Stripe al crear Payment Intent: {e}")
        return None
