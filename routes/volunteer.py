from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from database import get_db, get_case_by_stripe_session_id 
from models import Case, User
from services.payment_service import create_volunteer_payment_session
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file, detect_file_type 
from config import STRIPE_WEBHOOK_SECRET, ADMIN_BYPASS_KEY 
import datetime
import uuid
import os
import stripe

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# --- LÓGICA DE PROCESAMIENTO ASÍNCRONO ---
def process_paid_case_task(case_id: int, db: Session):
    """Tarea de fondo para procesar el caso con la IA después del pago (o acceso gratuito)."""
    
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        print(f"ERROR TAREA: Caso {case_id} no encontrado para procesamiento de IA.")
        return

    try:
        print(f"INFO TAREA: Iniciando análisis de IA para caso {case.id}.")
        ai_result = analyze_case(case.description, case.file_path) 
        
        case.ai_result = ai_result
        case.status = "completed"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
        print(f"INFO TAREA: Caso {case.id} completado con éxito.")

    except Exception as e:
        print(f"ERROR TAREA: Fallo en el análisis de IA para caso {case.id}: {str(e)}")
        case.status = "error"
        case.ai_result = f"Error de procesamiento de IA: {str(e)}"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
    
    finally:
        db.close() 

# ------------------------------------------------------------------
# --- ENDPOINT 1: CREAR CASO Y GENERAR PAGO (O BYPASS) ---
# ------------------------------------------------------------------

@router.post("/create-case")
async def create_case(
    user_id: int = Form(...),
    description: str = Form(...),
    has_legal_consent: bool = Form(...),
    file: UploadFile = File(None),
    
    # 🔑 CORRECCIÓN DEL SYNTAX ERROR: background_tasks se mueve a esta posición
    background_tasks: BackgroundTasks, 
    
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    if not has_legal_consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento legal para enviar y procesar el caso.")

    file_path = None
    case_title = description[:50] if description else f"Caso Voluntario {user_id}-{datetime.datetime.utcnow().timestamp()}"

    # 1. Manejo y Anonimización del Archivo
    if file:
        file_type = detect_file_type(file.filename)
        # Revisión de tipo de contenido para mayor seguridad
        if file_type == "unknown" and file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
            raise HTTPException(status_code=400, detail="Tipo de archivo no soportado o desconocido. Solo se permiten imágenes o PDF.")

        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_dir = os.environ.get("FILE_STORAGE_PATH", "temp") 
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, filename)
        
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        anonymize_file(temp_path, file_type) 
        file_path = temp_path

    # ----------------------------------------------------------------------
    # 🔑 LÓGICA DE ACCESO GRATUITO PARA DESARROLLADOR (BYPASS DE PAGO) 🔑
    # ----------------------------------------------------------------------
    developer_email = "maykel75122805321@gmail.com"
    free_access_key = "maykel-free-access" 

    if user.email == developer_email or ADMIN_BYPASS_KEY == free_access_key:
        
        new_case = Case(
            volunteer_id=user_id,
            title=case_title,
            description=description,
            file_path=file_path,
            status="processing", 
            has_legal_consent=has_legal_consent,
            is_paid=True,
            created_at=datetime.datetime.utcnow(),
            stripe_session_id="DEVELOPER_FREE_ACCESS"
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)

        db_session_for_task = get_db().__next__() 
        background_tasks.add_task(process_paid_case_task, new_case.id, db_session_for_task)

        return {
            "message": "Caso procesado gratis como desarrollador.",
            "case_id": new_case.id,
            "status": "processing"
        }
    # ----------------------------------------------------------------------
    # FIN DEL BYPASS. CONTINÚA EL FLUJO NORMAL (PAGO REQUERIDO)
    # ----------------------------------------------------------------------

    # 2. Crear caso inicial en DB (status: awaiting_payment)
    new_case = Case(
        volunteer_id=user_id,
        title=case_title,
        description=description,
        file_path=file_path,
        status="awaiting_payment",
        has_legal_consent=has_legal_consent,
        is_paid=False,
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 3. Crear sesión de pago en Stripe
    try:
        payment_session_data = create_volunteer_payment_session(
            user_email=user.email,
            case_price=50,
            metadata={"case_id": new_case.id}, 
            success_url=f"https://ateneoclinicoia.onrender.com/success?case_id={new_case.id}",
            cancel_url="https://ateneoclinicoia.onrender.com/cancel"
        )
        if "error" in payment_session_data:
            raise Exception(payment_session_data["error"])
        
        new_case.stripe_session_id = payment_session_data.get("id")
        db.commit()

    except Exception as e:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error en la creación de la sesión de pago: {str(e)}")

    # 5. Respuesta para redirección a Stripe
    return {
        "message": "Caso enviado. Redirigiendo a pago Stripe.",
        "case_id": new_case.id,
        "payment_url": payment_session_data["url"]
    }

# ------------------------------------------------------------------
# --- ENDPOINT 2: WEBHOOK DE STRIPE (ACTIVACIÓN DE IA) ---
# ------------------------------------------------------------------

@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        stripe_session_id = session.get("id")
        
        # Buscar caso usando el session ID
        case = db.query(Case).filter(Case.stripe_session_id == stripe_session_id).first()
        
        if not case or case.is_paid:
            return {"status": "success", "message": "Case not found or already processed."}

        case.is_paid = True
        case.status = "paid"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
        
        db_session_for_task = get_db().__next__()
        background_tasks.add_task(process_paid_case_task, case.id, db_session_for_task)

    return {"status": "success"}

# ------------------------------------------------------------------
# --- ENDPOINT DE LECTURA DE CASOS ---
# ------------------------------------------------------------------

@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role.in_(["volunteer", "professional"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    
    cases = db.query(Case).filter(Case.volunteer_id == user_id).all()
    
    return [
        {
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "is_paid": c.is_paid,
            "ai_result": c.ai_result if c.is_paid and c.status == "completed" else "Análisis en progreso o pago pendiente."
        } for c in cases
    ]
