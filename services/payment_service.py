import stripe
# La clave se inicializa en config.py, no necesitamos importarla aquí si ya está global.

def create_payment_session(case_id: int, price: int, success_url: str, cancel_url: str, product_name: str):
    """Crea una sesión de Stripe Checkout para pago por redirección."""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(price * 100), 
                    'product_data': {'name': product_name},
                },
                'quantity': 1,
            }],
            mode='payment',
            metadata={"case_id": case_id}, # CRÍTICO: Para identificar el caso al regreso
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"id": session.id, "url": session.url}
    except stripe.error.StripeError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Error desconocido: {str(e)}"}
