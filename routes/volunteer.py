from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from database import get_db, get_case_by_stripe_session_id
from models import Case, User
from services.payment_service import create_volunteer_payment_session
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file, detect_file_type # 🔑 IMPORTACIÓN CORREGIDA
from config import STRIPE_WEBHOOK_SECRET, ADMIN_BYPASS_KEY # 🔑 IMPORTACIÓN NECESARIA
import datetime
import uuid
import os
import stripe

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# --- LÓGICA DE PROCESAMIENTO ASÍNCRONO ---
def process_paid_case_task(case_id: int, db: Session):
    """Tarea de fondo para procesar el caso con la IA después del pago (o acceso gratuito)."""
    
    # 1. Obtenemos el caso (necesitamos un nuevo DB Session para tareas de fondo)
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        print(f"ERROR TAREA: Caso {case_id} no encontrado para procesamiento de IA.")
        return

    # 2. Ejecutar análisis de IA
    try:
        print(f"INFO TAREA: Iniciando análisis de IA para caso {case.id}.")
        # NOTA: La función analyze_case ya maneja la subida/descarga/limpieza del archivo en Gemini
        ai_result = analyze_case(case.description, case.file_path) 
        
        # 3. Actualizar DB
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
        # 4. Asegurar que la sesión de DB se cierre
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
    background_tasks: BackgroundTasks, # 🔑 AÑADIDO: Necesario para la tarea de fondo
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    # 🚫 VERIFICACIÓN DE CONSENTIMIENTO ANTES DE CONTINUAR
    if not has_legal_consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento legal para enviar y procesar el caso.")

    file_path = None
    case_title = description[:50] if description else f"Caso Voluntario {user_id}-{datetime.datetime.utcnow().timestamp()}"

    # 1. Manejo y Anonimización del Archivo (Lógica base)
    if file:
        file_type = detect_file_type(file.filename)
        if file_type == "unknown":
             raise HTTPException(status_code=400, detail="Tipo de archivo no soportado.")
             
        # Guardar archivo temporalmente
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # Anonimizar (sobrescribe el archivo en temp_path con un archivo de referencia)
        anonymize_file(temp_path, file_type) 
        file_path = temp_path # Usamos la ruta temporal con el contenido anonimizado

    # ----------------------------------------------------------------------
    # 🔑 LÓGICA DE ACCESO GRATUITO PARA DESARROLLADOR (BYPASS DE PAGO) 🔑
    # ----------------------------------------------------------------------
    developer_email = "maykel75122805321@gmail.com"
    free_access_key = "maykel-free-access" # Debe coincidir con el valor en la variable de entorno

    if user.email == developer_email or ADMIN_BYPASS_KEY == free_access_key:
        
        # Crear caso en DB (status: processing, is_paid=True por bypass)
        new_case = Case(
            volunteer_id=user_id,
            title=case_title,
            description=description,
            file_path=file_path,
            status="processing",
            has_legal_consent=has_legal_consent,
            is_paid=True,
            created_at=datetime.datetime.utcnow(),
            stripe_session_id="DEVELOPER_FREE_ACCESS" # Marcador
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)

        # Ejecutar IA directamente en background
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
    db.refresh(new_case) # Necesitamos el ID del caso antes de Stripe

    # 3. Crear sesión de pago en Stripe
    try:
        payment_session_data = create_volunteer_payment_session(
            user_email=user.email,
            case_price=50,
            metadata={"case_id": new_case.id}, 
            # NOTA: Usar el ID del caso en la URL de éxito para mostrar un mensaje
            success_url=f"/success?case_id={new_case.id}" 
        )
        if "error" in payment_session_data:
            raise Exception(payment_session_data["error"])
        
        # 4. Actualizar el caso con el ID de sesión de Stripe
        new_case.stripe_session_id = payment_session_data.get("id")
        db.commit()

    except Exception as e:
        # Limpieza y rollback si Stripe falla
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
# --- ENDPOINT 2: WEBHOOK DE STRIPE (ACTIVA LA IA) ---
# ------------------------------------------------------------------
# NOTA: Esta ruta debería idealmente estar en routes/stripe_webhook.py
# pero se mantiene aquí para conveniencia si usas un solo router principal.

@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    # 1. Obtener la firma y el cuerpo del evento
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    event = None

    # 2. Verificar el evento de Stripe (Seguridad)
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Firma no válida
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        # Firma no válida
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 3. Manejar el evento de pago exitoso
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        # Obtener el ID de sesión y buscar el caso en la DB
        stripe_session_id = session.get("id")
        case = get_case_by_stripe_session_id(db, stripe_session_id)
        
        if not case:
            print(f"ERROR WEBHOOK: Caso no encontrado para session_id: {stripe_session_id}")
            return {"status": "success", "message": "Case not found but webhook processed."}

        if case.is_paid:
            print(f"ADVERTENCIA WEBHOOK: Caso {case.id} ya marcado como pagado.")
            return {"status": "success", "message": "Case already processed."}

        # 4. Actualizar el caso como pagado y cambiar el estado
        case.is_paid = True
        case.status = "paid"
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
        
        print(f"INFO WEBHOOK: Pago exitoso para caso {case.id}. Activando tarea de IA.")

        # 5. ACTIVAR LA TAREA DE IA EN SEGUNDO PLANO
        # La función de tarea de fondo necesita su propia sesión de DB
        background_tasks.add_task(process_paid_case_task, case.id, get_db().__next__())

    return {"status": "success"}

# ------------------------------------------------------------------
# --- ENDPOINT DE LECTURA (Manteniendo la ruta de casos) ---
# ------------------------------------------------------------------

@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    
    cases = db.query(Case).filter(Case.volunteer_id == user_id).all()
    
    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "status": c.status,
            "ai_result": c.ai_result,
            "is_paid": c.is_paid,
        } for c in cases
    ]
