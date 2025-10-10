from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Case 
from config import STRIPE_WEBHOOK_SECRET, GEMINI_API_KEY # Necesitas el Webhook Secret y la clave IA
from services.ai_service import analyze_case # Necesitas la función de análisis
import stripe
import json

router = APIRouter(prefix="/stripe", tags=["Stripe Webhook"])

# CRUCIAL: Configura tu clave secreta de Stripe aquí (o en tu archivo de configuración)
# stripe.api_key = STRIPE_SECRET_KEY 
# Asegúrate de que esto se haga globalmente o se pase a tu función de servicio.

@router.post("/webhook")
async def stripe_webhook_endpoint(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get('stripe-signature')

    # 1. VERIFICAR LA FIRMA DE SEGURIDAD (ANTI-FRAUDE)
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Firma de la solicitud inválida
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Fallo de la clave STRIPE_WEBHOOK_SECRET
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2. PROCESAR EL EVENTO DE PAGO EXITOSO
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Recuperar metadatos (necesarios para encontrar el caso)
        metadata = session.get('metadata')
        if not metadata:
            print("Webhook: Metadatos del caso no encontrados. Fallo al otorgar servicio.")
            return {"status": "ignored", "reason": "No metadata"}

        # Asumimos que guardaste el ID del caso en la metadata al crear la sesión
        # CRUCIAL: Si no guardaste el case_id en la metadata en el paso 1, tendrás que buscar 
        # el caso usando la descripción o user_id (lo cual es menos fiable).
        # Para este ejemplo, buscamos por user_id y status 'awaiting_payment'
        
        case_to_analyze = db.query(Case).filter(
            Case.user_id == int(metadata.get('user_id')),
            Case.status == "awaiting_payment"
            # Mejorar esta lógica si es necesario
        ).first()

        if case_to_analyze:
            # 3. OTORGAR SERVICIO: Ejecutar el análisis de IA
            try:
                ai_result = analyze_case(case_to_analyze.description, case_to_analyze.file_path)
                
                # Actualizar el caso en la base de datos
                case_to_analyze.ai_result = ai_result
                case_to_analyze.status = "analyzed"
                db.commit()
                print(f"Webhook: Caso {case_to_analyze.id} ANALIZADO y servicio otorgado tras pago exitoso.")
            except Exception as e:
                # Si la IA falla DESPUÉS del pago, marcar como error para revisión manual
                case_to_analyze.status = "error"
                db.commit()
                print(f"Webhook: Error al analizar caso {case_to_analyze.id} después del pago: {str(e)}")
        else:
            print(f"Webhook: Pago recibido, pero no se encontró caso pendiente.")


    # 4. Respuesta exitosa (Stripe necesita un 200 para no reintentar)
    return {"status": "success"}
