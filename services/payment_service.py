import stripe
from config import STRIPE_SECRET_KEY, RENDER_APP_URL # Necesitas la URL de tu app en Render

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
            # URL a la que Stripe redirige tras el éxito o el fallo
            success_url=RENDER_APP_URL + '/success.html', # Asegúrate de tener estas páginas
            cancel_url=RENDER_APP_URL + '/cancel.html',
            # PRE-RELLENAR información del cliente
            customer_email=user_email,
            # 🔑 CRÍTICO: Adjuntar metadatos para que el webhook sepa qué caso actualizar
            metadata=metadata
        )
        
        return {"url": session.url}

    except Exception as e:
        # Esto captura errores de API de Stripe (ej: clave incorrecta, precio malformado)
        return {"error": f"Error al crear sesión de Stripe: {str(e)}"}
