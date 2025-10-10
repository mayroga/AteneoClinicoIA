from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.payment_service import create_volunteer_payment_session
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file
import datetime
import uuid
import os
# =================================================================
# IMPORTACIÓN CRUCIAL DE LA CLAVE DE ADMINISTRADOR
from config import ADMIN_BYPASS_KEY 
# =================================================================

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# Subida de caso clínico por voluntario
@router.post("/submit-case")
async def submit_case(
    user_id: int = Form(...),
    description: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    # =============================================================
    # CAPTURA DE LA CLAVE SECRETA DEL ENCABEZADO HTTP
    x_admin_key: str = Header(None) 
    # =============================================================
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    payment_session_data = None
    is_admin_bypass = False

    # =============================================================
    # LÓGICA DE VERIFICACIÓN DE ACCESO GRATUITO/ILIMITADO
    # =============================================================
    if x_admin_key and x_admin_key == ADMIN_BYPASS_KEY:
        # 1. ACCESO CONCEDIDO: Se omite la llamada a Stripe.
        is_admin_bypass = True
        print(f"ADMIN BYPASS ACTIVO: {user.email} obtiene acceso ilimitado y gratuito.")
    else:
        # 2. ACCESO NORMAL: Se requiere crear la sesión de pago con Stripe.
        try:
            payment_session_data = create_volunteer_payment_session(user_email=user.email, case_price=50)
            
            if "error" in payment_session_data:
                raise Exception(payment_session_data["error"])

        except Exception as e:
            # Si la sesión de pago falla, se lanza una excepción
            raise HTTPException(status_code=400, detail=f"Error en la creación de la sesión de pago: {str(e)}")

    # =============================================================
    # CONTINUACIÓN DEL PROCESAMIENTO DEL CASO (Común para Admin y Pagadores)
    # =============================================================
    
    file_path = None
    if file:
        # Guardar archivo temporal
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        # Anonimizar archivo
        file_path = anonymize_file(temp_path)

    # Nota: Tu modelo 'Case' requiere un 'title'.
    case_title = description[:50] if description else f"Caso Voluntario {user_id}-{datetime.datetime.utcnow().timestamp()}"
    
    new_case = Case(
        user_id=user_id,
        title=case_title, 
        description=description,
        file_path=file_path,
        status="pending",
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Analizar caso con IA
    try:
        # Aquí se usa la clave de GEMINI para el análisis
        ai_result = analyze_case(description, file_path)
        new_case.ai_result = ai_result
        new_case.status = "analyzed"
        db.commit()
        ai_result_message = "Analizado correctamente (Gratis)" if is_admin_bypass else "Analizado correctamente (Sujeto a Pago Stripe)"
    except Exception as e:
        new_case.status = "error"
        db.commit()
        # Si el análisis de IA falla, lanzamos una excepción 500
        raise HTTPException(status_code=500, detail=f"Error al analizar el caso: {str(e)}")

    return {
        "message": ai_result_message,
        "case_id": new_case.id,
        "ai_result": new_case.ai_result,
        # Devolvemos la URL de pago SOLO si no fue un bypass de administrador
        "payment_url": payment_session_data["url"] if payment_session_data else None
    }

# Consulta de casos previos del voluntario (sin cambios)
@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    
    # Asumo que la llave foránea correcta en tu modelo Case es Case.user_id
    cases = db.query(Case).filter(Case.user_id == user_id).all() 
    
    return [
        {
            "id": c.id, 
            "title": c.title,
            "description": c.description, 
            "status": c.status, 
            "ai_result": c.ai_result
        } for c in cases
    ]
