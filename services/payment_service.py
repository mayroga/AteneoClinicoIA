import stripe
from config import STRIPE_SECRET_KEY, RENDER_APP_URL

# CRÍTICO: Inicializar Stripe con la clave secreta
stripe.api_key = STRIPE_SECRET_KEY

def create_volunteer_payment_session(user_email: str, case_price: int, metadata: dict):
    """Crea una sesión de pago de Stripe Checkout para un caso de voluntario."""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': case_price * 100,  # Convertir a centavos
                        'product_data': {
                            'name': 'Análisis Clínico por IA',
                            'description': 'Análisis de caso de voluntario por el Ateneo Clínico IA.',
                        },
                    },
                    'quantity': 1,
                }
            ],
            mode='payment',
            success_url=RENDER_APP_URL + '/success.html',
            cancel_url=RENDER_APP_URL + '/cancel.html',
            customer_email=user_email,
            metadata=metadata
        )
        
        return {"url": session.url}

    except Exception as e:
        return {"error": f"Error al crear sesión de Stripe: {str(e)}"}


def get_all_payments(limit: int = 100):
    """
    Recupera una lista de pagos (PaymentIntents) o cargos exitosos de Stripe.
    Se usa en el panel de administración.
    """
    if not STRIPE_SECRET_KEY:
        return {"error": "Stripe no configurado."}

    try:
        # Recuperamos la lista de PaymentIntents exitosos
        payments = stripe.PaymentIntent.list(limit=limit, status='succeeded')
        
        # Opcional: Procesar y limpiar los datos para devolver solo lo necesario
        processed_payments = []
        for payment in payments.data:
            processed_payments.append({
                "id": payment.id,
                "amount": payment.amount / 100, # Devolver en USD
                "currency": payment.currency.upper(),
                "created": payment.created, # Timestamp
                "description": payment.description,
                "customer_email": payment.receipt_email # Email del recibo
            })
        
        return processed_payments

    except Exception as e:
        return {"error": f"Error al recuperar pagos de Stripe: {str(e)}"}
