from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from database import get_db, get_case_by_stripe_session_id # Asegúrate de tener get_case_by_stripe_session_id en database.py
from models import Case, User
from services.payment_service import create_volunteer_payment_session
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file, detect_file_type # 🔑 IMPORTACIONES CORREGIDAS
from config import STRIPE_WEBHOOK_SECRET, ADMIN_BYPASS_KEY # 🔑 IMPORTACIONES NECESARIAS
import datetime
import uuid
import os
import stripe

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# --- LÓGICA DE PROCESAMIENTO ASÍNCRONO ---
def process_paid_case_task(case_id: int, db: Session):
    """Tarea de fondo para procesar el caso con la IA después del pago (o acceso gratuito)."""
    
    # NOTA: En un entorno de producción real, se debería inicializar la sesión de DB
    # dentro de la tarea usando un patrón de contexto o una nueva conexión.
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        print(f"ERROR TAREA: Caso {case_id} no encontrado para procesamiento de IA.")
        return

    try:
        print(f"INFO TAREA: Iniciando análisis de IA para caso {case.id}.")
        # Llama al servicio de IA para el análisis
        ai_result = analyze_case(case.description, case.file_path) 
        
        # Actualizar DB
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
        # Asegurar que la sesión de DB se cierre si la tarea la abrió
        db.close() 

# ------------------------------------------------------------------
# --- ENDPOINT 1: CREAR CASO Y GENERAR PAGO (O BYPASS) ---
# ------------------------------------------------------------------

@router.post("/create-case")
async def create_case(
    user_id: int = Form(...), # Asume que este ID viene del cliente después de la autenticación
    description: str = Form(...),
    has_legal_consent: bool = Form(...),
    file: UploadFile = File(None),
    background_tasks: BackgroundTasks, # 🔑 AÑADIDO: Necesario para la tarea de fondo de IA
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
        if file_type == "unknown" or file_type == "text": # Los PDFs/archivos médicos deben manejarse con cuidado
             # Permite solo tipos específicos si la IA está configurada para ellos
             if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
                raise HTTPException(status_code=400, detail="Tipo de archivo no soportado o desconocido. Solo se permiten imágenes o PDF.")

        # Guardar archivo temporalmente
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_dir = os.environ.get("FILE_STORAGE_PATH", "temp") # Usa variable de entorno o 'temp'
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, filename)
        
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # Anonimizar (sobrescribe el archivo con un archivo de referencia)
        anonymize_file(temp_path, file_type) 
        file_path = temp_path # La ruta al archivo anonimizado

    # ----------------------------------------------------------------------
    # 🔑 LÓGICA DE ACCESO GRATUITO PARA DESARROLLADOR (BYPASS DE PAGO) 🔑
    # ----------------------------------------------------------------------
    developer_email = "maykel75122805321@gmail.com"
    free_access_key = "maykel-free-access" 

    # Condición: Si el email coincide O si el ADMIN_BYPASS_KEY está configurado para acceso gratuito
    if user.email == developer_email or ADMIN_BYPASS_KEY == free_access_key:
        
        # Crear caso en DB (is_paid=True por bypass)
        new_case = Case(
            volunteer_id=user_id,
            title=case_title,
            description=description,
            file_path=file_path,
            status="processing", # Inicia procesamiento inmediatamente
            has_legal_consent=has_legal_consent,
            is_paid=True,
            created_at=datetime.datetime.utcnow(),
            stripe_session_id="DEVELOPER_FREE_ACCESS" 
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)

        # Ejecutar IA directamente en background
        db_session_for_task = get_db().__next__() # Obtener una nueva sesión para la tarea
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
            case_price=50, # Precio fijo de 50 USD
            metadata={"case_id": new_case.id}, 
            success_url=f"https://ateneoclinicoia.onrender.com/success?case_id={new_case.id}",
            cancel_url="https://ateneoclinicoia.onrender.com/cancel" # URL de cancelación
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
# --- ENDPOINT 2: WEBHOOK DE STRIPE (CRÍTICO PARA LA ACTIVACIÓN DE IA) ---
# ------------------------------------------------------------------
# NOTA: Esta ruta debería estar expuesta como POST en /volunteer/stripe-webhook
# en tu archivo principal (main.py) y configurada en el dashboard de Stripe.

@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    # 1. Obtener la firma y el cuerpo del evento
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    # 2. Verificar el evento de Stripe (Seguridad)
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 3. Manejar el evento de pago exitoso
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        # Obtener el ID de sesión
        stripe_session_id = session.get("id")
        # Asegúrate de que get_case_by_stripe_session_id use el campo stripe_session_id
        case = db.query(Case).filter(Case.stripe_session_id == stripe_session_id).first()
        
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
        # Necesitamos una nueva sesión de DB para la tarea de fondo.
        background_tasks.add_task(process_paid_case_task, case.id, get_db().__next__())

    return {"status": "success"}

# ------------------------------------------------------------------
# --- ENDPOINT DE LECTURA DE CASOS ---
# ------------------------------------------------------------------

@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    # Esta ruta debería usar una dependencia de autenticación (JWT) para obtener el ID,
    # en lugar de recibirlo directamente en la URL, por razones de seguridad.
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
            # Solo mostrar el resultado de la IA si el caso está pagado y completado
            "ai_result": c.ai_result if c.is_paid and c.status == "completed" else "Análisis en progreso o pago pendiente."
        } for c in cases
    ]
