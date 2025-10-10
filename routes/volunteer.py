# Archivo a identificar: routes/volunteer.py

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.payment_service import create_volunteer_payment_session
from services.ai_service import analyze_case 
from services.anonymizer import anonymize_file
from config import ADMIN_BYPASS_KEY 
import datetime
import uuid
import os

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# =================================================================
# RUTA PRINCIPAL DE SERVICIO (CORREGIDA PARA EL FLUJO SEGURO Y BYPASS)
# =================================================================
@router.post("/submit-case")
async def submit_case(
    user_id: int = Form(...),
    description: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    # Captura del encabezado para el bypass de administrador
    x_admin_key: str = Header(None) 
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    file_path = None
    if file:
        # Guardar archivo temporal y anonimizar
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        file_path = anonymize_file(temp_path)

    case_title = description[:50] if description else f"Caso Voluntario {user_id}-{datetime.datetime.utcnow().timestamp()}"
    payment_session_data = None
    is_admin_bypass = False
    case_status = "awaiting_payment"

    # 1. LÓGICA DE BYPASS DE ADMINISTRADOR (GRATIS/ILIMITADO)
    if x_admin_key and x_admin_key == ADMIN_BYPASS_KEY:
        is_admin_bypass = True
        case_status = "paid" # Marcamos como pagado para el flujo inmediato
        print(f"ADMIN BYPASS ACTIVO: {user.email} obtiene acceso ilimitado.")
    else:
        # 2. LÓGICA DE USUARIO NORMAL (Requiere Stripe)
        try:
            # La sesión se crea para el PAGO del caso
            payment_session_data = create_volunteer_payment_session(
                user_email=user.email, 
                case_price=50,
                # Usamos metadata para identificar el caso más tarde en el webhook
                metadata={"user_id": user_id, "description": case_title}
            )
            if "error" in payment_session_data:
                raise Exception(payment_session_data["error"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error en la creación de la sesión de pago: {str(e)}")

    # 3. Guardar Caso en DB
    new_case = Case(
        user_id=user_id,
        title=case_title,
        description=description,
        file_path=file_path,
        status=case_status, 
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 4. SI ES ADMIN, PROCESAR EL CASO INMEDIATAMENTE
    if is_admin_bypass:
        try:
            ai_result = analyze_case(description, file_path)
            new_case.ai_result = ai_result
            new_case.status = "analyzed"
            db.commit()
            return {
                "message": "Caso enviado y analizado (ACCESO ILIMITADO/GRATUITO)",
                "case_id": new_case.id,
                "ai_result": ai_result,
            }
        except Exception as e:
            new_case.status = "error"
            db.commit()
            raise HTTPException(status_code=500, detail=f"Error al analizar el caso de Admin: {str(e)}")


    # 5. RESPUESTA para USUARIO NORMAL (Redirección a Pago)
    return {
        "message": "Caso enviado. Redirigiendo a pago Stripe.",
        "case_id": new_case.id,
        "payment_url": payment_session_data["url"]
    }

# Consulta de casos previos del voluntario (se mantiene)
@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    
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
