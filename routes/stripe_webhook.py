from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Case 
from config import STRIPE_WEBHOOK_SECRET
from services.ai_service import analyze_case 
import stripe
import json

router = APIRouter(tags=["Stripe Webhook"])

# CRUCIAL: Inicializar Stripe aquí para el Webhook (ya que el servicio lo hace en payment_service)
# Asegúrate de que tu STRIPE_SECRET_KEY se configure globalmente si es necesario, o pásalo aquí si no.
# Asumo que se inicializa en otro lugar o que la librería stripe ya lo tiene configurado.

@router.post("/stripe/webhook")
async def stripe_webhook_endpoint(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')

    # 1. VERIFICAR LA FIRMA DE SEGURIDAD
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. PROCESAR EL EVENTO DE PAGO EXITOSO
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata')
        
        if not metadata or 'user_id' not in metadata:
            return {"status": "ignored", "reason": "No metadata or user_id"}

        user_id = int(metadata.get('user_id'))
        
        # Buscar el caso más reciente pendiente de pago
        case_to_analyze = db.query(Case).filter(
            Case.user_id == user_id,
            Case.status == "awaiting_payment"
        ).order_by(Case.created_at.desc()).first()

        if case_to_analyze:
            # 3. OTORGAR SERVICIO: Ejecutar el análisis de IA
            try:
                ai_result = analyze_case(case_to_analyze.description, case_to_analyze.file_path)
                
                # Actualizar el caso en la base de datos
                case_to_analyze.ai_result = ai_result
                case_to_analyze.status = "analyzed"
                db.commit()
            except Exception as e:
                # Marcar como error para revisión manual
                case_to_analyze.status = "error"
                db.commit()
                # No lanzamos un 500 para Stripe; el webhook debe retornar 200
                print(f"Error al analizar caso {case_to_analyze.id} después del pago: {str(e)}")
        else:
            print(f"Pago recibido, pero no se encontró caso pendiente para user_id {user_id}")

    # 4. Respuesta exitosa (Stripe necesita un 200 OK)
    return {"status": "success"}
