import stripe
import json
import psycopg2.extras
from typing import Optional, Dict, Any

from config import settings
from database import get_db_connection # Asumiendo que esta utilidad existe
from models import CreatePaymentIntent # Asumiendo que este modelo existe

# Configura Stripe con tu clave secreta
stripe.api_key = settings.STRIPE_SECRET_KEY

# ----------------------------------------------------
# LÓGICA DE ACTUALIZACIÓN DE ESTADO EN DB
# ----------------------------------------------------

def update_user_status_after_payment(email: str, user_type: str, amount: int) -> bool:
    """
    Actualiza el estado del usuario en la base de datos tras un pago exitoso.
    El 'amount' es el monto pagado en la moneda más pequeña (e.g., centavos USD).
    """
    conn = get_db_connection()
    if conn is None:
        print("ERROR DB: No se pudo conectar a la base de datos para actualizar el estado.")
        return False
    
    try:
        cursor = conn.cursor()
        
        if user_type == 'volunteer':
            # Lógica para Voluntarios (asume que el pago valida su registro para subir un caso)
            # En un sistema real, aquí se actualizaría una columna 'payment_status' para desbloquear la subida de casos.
            print(f"INFO: Pago de voluntario {email} exitoso. Acceso habilitado.")
            # Si tienes una tabla de 'volunteers' podrías hacer un UPDATE aquí:
            # cursor.execute("UPDATE volunteers SET is_paid = TRUE WHERE email = %s;", (email,))
            
        elif user_type == 'professional':
            # Lógica para Profesionales: Asignar créditos por el pago.
            credits_to_add = 10 # Se asignan 10 créditos por el pago de la cuota profesional
            
            cursor.execute(
                """
                UPDATE professionals 
                SET credits = credits + %s 
                WHERE email = %s 
                RETURNING credits;
                """,
                (credits_to_add, email)
            )
            
            if cursor.rowcount == 0:
                print(f"ADVERTENCIA: Profesional {email} no encontrado para asignar créditos. Se requiere registro previo.")
                conn.rollback()
                return False

            new_credits = cursor.fetchone()[0]
            print(f"INFO: Pago de profesional {email} exitoso. {credits_to_add} créditos asignados. Total: {new_credits}.")
        
        conn.commit()
        return True
    
    except Exception as e:
        conn.rollback()
        print(f"ERROR DB al procesar webhook para {email}: {e}")
        return False
    finally:
        if conn: conn.close()


# ----------------------------------------------------
# LÓGICA DE PASARELA (PAGO DIRECTO)
# ----------------------------------------------------

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

# ----------------------------------------------------
# LÓGICA DE WEBHOOK (EVENTOS ASÍNCRONOS)
# ----------------------------------------------------

def handle_webhook_event(payload: bytes, sig_header: str) -> bool:
    """
    Verifica la firma del webhook y procesa el evento de Stripe.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        print("ERROR: STRIPE_WEBHOOK_SECRET no configurado. El webhook no puede ser verificado.")
        return False

    try:
        # 1. Construir el Evento (Verificación de la Firma)
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        
        event_type = event['type']
        
        if event_type == 'checkout.session.completed':
            session = event['data']['object']
            
            # Obtener datos relevantes de la sesión de checkout (metadata que enviamos al crear la sesión)
            user_email = session.get('customer_details', {}).get('email') or session.get('metadata', {}).get('user_email')
            user_type = session.get('metadata', {}).get('user_type')
            
            # El monto total de la sesión (en la moneda más pequeña)
            total_amount = session.get('amount_total')
            
            if user_email and user_type and total_amount is not None:
                print(f"WEBHOOK INFO: Pago completado para {user_email} ({user_type}). Monto: {total_amount}.")
                # 2. Actualizar el estado del usuario en la base de datos
                return update_user_status_after_payment(user_email, user_type, total_amount)
            else:
                print(f"WEBHOOK ADVERTENCIA: Datos de sesión incompletos para el evento {event_type}. Email: {user_email}, Tipo: {user_type}, Monto: {total_amount}.")
                return False

        elif event_type == 'payment_intent.succeeded':
            # Se podría usar si el profesional paga con Payment Intent
            print(f"WEBHOOK INFO: Evento Payment Intent Succeeded. Ignorando para enfocarnos en Checkout Session Completed.")
            return True

        else:
            # Ignorar otros tipos de eventos
            print(f"WEBHOOK INFO: Evento Stripe ignorado: {event_type}")
            return True

    except ValueError as e:
        # Error al parsear el payload
        print(f"WEBHOOK ERROR: Invalid payload: {e}")
        return False
    except stripe.error.SignatureVerificationError as e:
        # Error de verificación de firma
        print(f"WEBHOOK ERROR: Invalid signature: {e}")
        return False
    except Exception as e:
        # Otros errores
        print(f"WEBHOOK ERROR: Fallo al procesar el evento: {e}")
        return False

    return True
