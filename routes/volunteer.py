from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.payment_service import create_payment_session
from services.ai_service import analyze_case 
from services.anonymizer import anonymize_file, detect_file_type 
from config import ADMIN_BYPASS_KEY, BASE_URL
import datetime
import stripe 

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# --- LÓGICA DE PROCESAMIENTO ASÍNCRONO ---
def process_case_task(case_id: int, db: Session):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case: return
    try:
        # Aquí se llama al servicio de IA
        ai_result = analyze_case(case.description, case.file_path) 
        case.ai_result = ai_result
        case.status = "completed"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
    except Exception as e:
        case.status = "error"
        case.ai_result = f"Error de IA: {str(e)}"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
    finally:
        db.close() 

# ------------------------------------------------------------------
# --- ENDPOINT 1: CREAR CASO Y GENERAR SESIÓN DE PAGO O BYPASS ---
# ------------------------------------------------------------------

@router.post("/create-case")
async def create_case(
    background_tasks: BackgroundTasks, 
    user_id: int = Form(...),
    description: str = Form(...),
    has_legal_consent: bool = Form(...),
    developer_bypass_key: str = Form(None), 
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    if not has_legal_consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento legal")

    file_path = None
    case_title = description[:50] if description else f"Caso Voluntario {user_id}"
    case_price = 50 

    # Asumimos anonimización exitosa
    if file:
        file_bytes = await file.read()
        file_type = detect_file_type(file.filename)
        # Necesitamos el ID del caso para nombrar el archivo. Hacemos un commit para obtenerlo.
        
    # Lógica de Bypass
    if developer_bypass_key and developer_bypass_key == ADMIN_BYPASS_KEY:
        new_case = Case(
            volunteer_id=user_id, title=case_title, description=description, 
            file_path=file_path, status="processing", is_paid=True, 
            price_paid=case_price, has_legal_consent=has_legal_consent,
            stripe_session_id="DEVELOPER_FREE_ACCESS"
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)
        
        # Si se usa bypass y hay archivo, anonimizar ahora
        if file:
            file_path = anonymize_file(file_bytes, file_type, new_case.id)
            new_case.file_path = file_path
            db.commit()

        db_session_for_task = get_db().__next__()
        background_tasks.add_task(process_case_task, new_case.id, db_session_for_task)

        return {
            "message": "Caso activado por bypass. Resultados en breve.",
            "case_id": new_case.id,
            "status": "processing"
        }
        
    # FLUJO DE PAGO
    new_case = Case(
        volunteer_id=user_id, title=case_title, description=description,
        file_path=file_path, status="awaiting_payment", price_paid=case_price,
        has_legal_consent=has_legal_consent, is_paid=False
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Si hay archivo, anonimizar y actualizar la ruta después de tener el case_id
    if file:
        file_path = anonymize_file(file_bytes, file_type, new_case.id)
        new_case.file_path = file_path
        db.commit()
    
    try:
        payment_session_data = create_payment_session(
            case_id=new_case.id,
            price=case_price,
            product_name="Análisis de Caso Voluntario",
            success_url=f"{BASE_URL}/volunteer/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/volunteer/payment-cancel"
        )
        if "error" in payment_session_data: raise Exception(payment_session_data["error"])
        
        new_case.stripe_session_id = payment_session_data.get("id")
        db.commit()

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error en sesión de pago: {str(e)}")

    return {"message": "Redirigiendo a pago Stripe.", "payment_url": payment_session_data["url"]}

# ------------------------------------------------------------------
# --- ENDPOINT 2: ACTIVACIÓN TRAS REDIRECCIÓN DE PAGO EXITOSO ---
# ------------------------------------------------------------------

@router.get("/payment-success")
async def payment_success(
    session_id: str,
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status != "paid":
             return {"message": "Pago no completado. Estado: " + session.payment_status}
        
        case_id = session.metadata.get('case_id')
        if not case_id:
            raise HTTPException(status_code=400, detail="Error: Metadata de caso ausente.")

        case = db.query(Case).filter(Case.id == int(case_id)).first()
        
        if not case:
             raise HTTPException(status_code=404, detail="Caso no encontrado en DB.")
        
        # Marcar como pagado y activar IA 
        case.is_paid = True
        case.status = "processing"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
        
        # Ejecutar la IA en segundo plano
        db_session_for_task = get_db().__next__()
        background_tasks.add_task(process_case_task, case.id, db_session_for_task)

        return {"message": f"Pago verificado. Servicio ({case.id}) activado.", "case_id": case.id, "status": "processing"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al verificar pago o activar servicio: {str(e)}")

# ------------------------------------------------------------------
# --- ENDPOINT DE CANCELACIÓN ---
# ------------------------------------------------------------------

@router.get("/payment-cancel")
def payment_cancel():
    return {"message": "Pago cancelado. Vuelve a la página principal."}
