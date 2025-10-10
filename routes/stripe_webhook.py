from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Case # Asume que tienes un modelo Case en models.py
from config import STRIPE_WEBHOOK_SECRET 
from services.ai_service import analyze_case # Importa la función crítica
import stripe
import json

router = APIRouter(tags=["Stripe Webhook"])

# CRUCIAL: Este endpoint DEBE estar expuesto sin autenticación, ya que Stripe es quien llama.
@router.post("/stripe/webhook")
async def stripe_webhook_endpoint(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')

    # 1. VERIFICAR LA FIRMA DE SEGURIDAD (ANTI-FRAUDE)
    try:
        # Usa el STRIPE_WEBHOOK_SECRET de tu config.py
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Firma de la solicitud inválida
        print(f"Webhook Error: Invalid payload - {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Fallo de la clave STRIPE_WEBHOOK_SECRET (La clave en Render es incorrecta)
        print(f"Webhook Error: Invalid signature - {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. PROCESAR EL EVENTO DE PAGO EXITOSO
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # 🔑 CRÍTICO: Recuperar metadatos para encontrar el caso.
        metadata = session.get('metadata')
        if not metadata or 'user_id' not in metadata:
            print("Webhook: Metadatos insuficientes o user_id no encontrado.")
            return {"status": "ignored", "reason": "No metadata"}

        user_id = int(metadata.get('user_id'))
        
        # Buscar el caso pendiente de pago para ese usuario
        case_to_analyze = db.query(Case).filter(
            Case.user_id == user_id,
            Case.status == "awaiting_payment"
            # Nota: Si el caso se guarda inmediatamente, busca por el caso más reciente
        ).order_by(Case.created_at.desc()).first()

        if case_to_analyze:
            # 3. OTORGAR SERVICIO: Ejecutar el análisis de IA
            try:
                # La función analyze_case usa la descripción y el file_path guardado
                print(f"Webhook: Pago recibido. Iniciando análisis de IA para caso {case_to_analyze.id}")
                ai_result = analyze_case(case_to_analyze.description, case_to_analyze.file_path)
                
                # Actualizar el caso en la base de datos
                case_to_analyze.ai_result = ai_result
                case_to_analyze.status = "analyzed"
                db.commit()
                print(f"Webhook: Caso {case_to_analyze.id} ANALIZADO y servicio otorgado.")
            except Exception as e:
                # Si la IA falla DESPUÉS del pago, marcar como error para revisión manual
                case_to_analyze.status = "error"
                db.commit()
                print(f"Webhook: Error crítico al analizar caso {case_to_analyze.id} después del pago: {str(e)}")
        else:
            print(f"Webhook: Pago recibido, pero no se encontró caso pendiente para user_id {user_id}")

    # 4. Respuesta exitosa (Stripe necesita un 200 OK para no reintentar)
    return {"status": "success"}
