import stripe
from config import STRIPE_SECRET_KEY, STRIPE_CURRENCY

# Inicializar Stripe con la clave secreta
# Se asume que STRIPE_SECRET_KEY está definido en Render.
stripe.api_key = STRIPE_SECRET_KEY

def create_volunteer_payment_session(user_id: int):
    """
    Crea una sesión de checkout de Stripe para la suscripción de un voluntario.
    Nota: Debes configurar un 'price_id' de Stripe para el plan del voluntario.
    """
    # Usar un Price ID de prueba o de producción que definas en Stripe
    # ESTE VALOR DEBE EXISTIR EN TU CUENTA DE STRIPE
    VOLUNTEER_PRICE_ID = "price_XXXXXXXXXXXXXXXXXXX" 
    
    if not VOLUNTEER_PRICE_ID or VOLUNTEER_PRICE_ID == "price_XXXXXXXXXXXXXXXXXXX":
         raise ValueError("El PRICE_ID para voluntarios no está configurado correctamente en el servicio de pagos.")
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price': VOLUNTEER_PRICE_ID,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            # Usar URLs de éxito y cancelación que Render necesita para redireccionar
            success_url='https://your-render-domain.com/payment/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='https://your-render-domain.com/payment/cancel',
            client_reference_id=str(user_id), # Referencia interna del usuario
        )
        return session.url
    except stripe.error.StripeError as e:
        # Manejo de errores específicos de Stripe
        raise Exception(f"Error al crear sesión de Stripe: {str(e)}")
    except Exception as e:
        raise Exception(f"Error desconocido en el servicio de pagos: {str(e)}")

def get_all_payments():
    """
    Obtiene una lista de transacciones o pagos recientes para el panel de administración.
    """
    try:
        # Usamos el API de Stripe para obtener una lista de cargos recientes.
        # Puedes ajustar los parámetros (limit) según necesites.
        charges = stripe.Charge.list(limit=100)
        
        # Procesamos y devolvemos solo la información relevante
        payments = []
        for charge in charges.data:
            payments.append({
                "id": charge.id,
                "amount": charge.amount / 100,  # Convertir centavos a dólares
                "currency": charge.currency,
                "status": charge.status,
                "description": charge.description,
                "created": charge.created # Timestamp UNIX
            })
        
        return payments
        
    except stripe.error.StripeError as e:
        raise Exception(f"Error al obtener pagos de Stripe: {str(e)}")
    except Exception as e:
        # Este error podría ocurrir si la clave de Stripe no está definida (aunque ya lo verificamos)
        raise Exception(f"Error desconocido al listar pagos: {str(e)}")
