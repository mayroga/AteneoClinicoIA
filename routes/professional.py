from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import ProfessionalLevel, User, Case
# 💡 PLACEHOLDERS: Necesitarás implementar estos archivos y funciones
from services.payment_service import create_professional_subscription_session
# Las tareas de IA y Anonimización se asumen que existen o se reusan de routes/volunteer.py
# from services.ai_service import analyze_case 
# from services.anonymizer import anonymize_file 
import datetime
import uuid
import os

router = APIRouter(prefix="/professional", tags=["Professional"])

# --- PLACEHOLDER DE AUTENTICACIÓN Y SUBSCRIPCIÓN ---
# 💡 NOTA: En un sistema real, esta dependencia verificaría el JWT, traería el objeto User,
# y comprobaría que tiene una suscripción activa.
def get_current_professional_user(db: Session = Depends(get_db)):
    """Dependencia placeholder para asegurar que el usuario es un profesional."""
    # Lógica placeholder: Buscar un usuario con rol profesional
    # Esto debe ser reemplazado por la verificación de token JWT en 'utils.py'
    user_id = 2 # Dummy ID para simular un profesional (debe ser el ID real del token)
    user = db.query(User).filter(User.id == user_id, User.role == "professional").first()
    
    if not user:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo para profesionales.")
        
    # Lógica Real (PENDIENTE): Verificar el estado de la suscripción Stripe del usuario
    # if not user.is_subscribed: 
    #    raise HTTPException(status_code=402, detail="Pago requerido: El profesional no tiene una suscripción activa.")
    
    return user
# -----------------------------


# =================================================================
# 1. GESTIÓN DE PLANES DE SUSCRIPCIÓN
# =================================================================

@router.get("/plans")
def list_subscription_plans(db: Session = Depends(get_db)):
    """Lista todos los planes de suscripción disponibles para profesionales."""
    plans = db.query(ProfessionalLevel).all()
    # Devolvemos solo los datos necesarios
    return [
        {
            "id": p.id,
            "name": p.name,
            "monthly_fee": p.monthly_fee,
            "features": p.features
        }
        for p in plans
    ]

@router.post("/subscribe/{plan_id}")
def start_subscription(
    plan_id: int,
    user: User = Depends(get_current_professional_user), # Asegura que sea un profesional
    db: Session = Depends(get_db)
):
    """Crea una sesión de pago de Stripe para iniciar una suscripción recurrente."""
    plan = db.query(ProfessionalLevel).filter(ProfessionalLevel.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan de suscripción no encontrado.")

    # 💡 LÓGICA DE STIPE PENDIENTE: create_professional_subscription_session
    try:
        # Placeholder para llamar al servicio de Stripe para suscripciones recurrentes
        # Se asume que 'plan.price_id' es el Price ID de Stripe para el plan recurrente
        payment_session_data = create_professional_subscription_session(
            user_email=user.email,
            price_id=plan.price_id, 
            metadata={"user_id": user.id, "plan_id": plan.id}
        )
        
        # En una aplicación real, se podría actualizar el estado de la suscripción del usuario a 'pending' aquí.
        
        return {
            "message": f"Iniciando suscripción al plan '{plan.name}'. Redirigiendo a Stripe.",
            "payment_url": payment_session_data["url"]
        }
    except Exception as e:
        # Si Stripe falla, lanzamos una excepción
        raise HTTPException(status_code=400, detail=f"Error al crear sesión de suscripción: {str(e)}")

# =================================================================
# 2. PROCESAMIENTO DE CASOS ILIMITADO (Para profesionales suscritos)
# =================================================================

# Reutilizamos la lógica de procesamiento asíncrono del voluntario para la IA
# NOTA: En un proyecto real, se importarían las funciones analyze_case y anonymize_file
# para evitar duplicar código. Usamos una tarea dummy aquí para mantener la estructura.
def process_professional_case_task(case_id: int, db: Session):
    """Tarea de fondo para procesar el caso ilimitado con la IA."""
    # --- LOGICA DUMMY ---
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case: return
    
    try:
        # 💡 Aquí se llamaría a analyze_case(case.description, case.file_path)
        analysis_result = "Resultado de Análisis Ilimitado (IA Placeholder)"
        case.ai_result = analysis_result
        case.status = "completed"
    except Exception as e:
        case.status = "error"
        case.ai_result = f"Error de procesamiento de IA: {str(e)}"
    finally:
        case.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.close()
    # --------------------


@router.post("/submit-case-unlimited")
async def submit_case_unlimited(
    description: str = Form(...),
    has_legal_consent: bool = Form(True),
    file: UploadFile = File(None),
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # Aseguramos que solo un profesional suscrito pueda usar esta ruta
    user: User = Depends(get_current_professional_user) 
):
    """Permite a un profesional con suscripción activa enviar casos ilimitados para análisis."""

    if not has_legal_consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento legal.")

    file_path = None
    
    # 1. Manejo y Anonimización del Archivo
    if file:
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        # file_path = anonymize_file(temp_path) # 💡 Llamada real al servicio
        file_path = temp_path # Usamos la ruta temporal como placeholder

    case_title = description[:50] if description else f"Caso Profesional {user.id}-{datetime.datetime.utcnow().timestamp()}"

    # 2. Crear caso en DB (status: processing, is_paid=True por suscripción)
    new_case = Case(
        volunteer_id=user.id, # El ID del remitente
        title=case_title,
        description=description,
        file_path=file_path,
        status="processing",
        is_paid=True, # Pagado a través de suscripción activa
        has_legal_consent=has_legal_consent,
        created_at=datetime.datetime.utcnow(),
        stripe_session_id="PROFESSIONAL_SUB" # Marcador para suscripción
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 3. Procesar el Caso Inmediatamente con la IA en segundo plano
    db_session_for_task = get_db().__next__()
    background_tasks.add_task(process_professional_case_task, new_case.id, db_session_for_task)

    return {
        "message": "Caso profesional enviado. El análisis de IA ilimitado ha comenzado en segundo plano.",
        "case_id": new_case.id,
        "status": "processing"
    }
