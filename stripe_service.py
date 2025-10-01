from config import settings
from models import CreatePaymentIntent
from typing import Optional

# NOTA: En producción, necesitarías la librería 'stripe' aquí.

def create_payment_intent(data: CreatePaymentIntent) -> Optional[dict]:
    """
    Simula la creación de un Payment Intent de Stripe usando la clave secreta.
    """
    # En producción: stripe.api_key = settings.STRIPE_SECRET_KEY
    # Aquí se haría la llamada a Stripe y se manejarían los errores.
    
    try:
        # Simulación de respuesta exitosa de Stripe
        if data.amount < 1: # Fallo simulado
            raise Exception("Monto invalido.")
            
        return {
            "client_secret": f"pi_{data.amount}_secret_demo_{data.product_type}",
            "payment_intent_id": f"pi_{data.amount}_demo_id",
            "amount": data.amount
        }
    except Exception as e:
        print(f"Error al crear la intención de pago (Simulado): {e}")
        return None
