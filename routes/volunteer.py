from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.payment_service import create_volunteer_payment_session
# ELIMINAMOS la importación de analyze_case de aquí
# from services.ai_service import analyze_case 
from services.anonymizer import anonymize_file
from config import ADMIN_BYPASS_KEY 
import datetime
import uuid
import os

router = APIRouter(prefix="/volunteer", tags=["volunteer"])

# Subida de caso clínico por voluntario
@router.post("/submit-case")
async def submit_case(
    user_id: int = Form(...),
    description: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    # =============================================================
    # CAPTURA DE LA CLAVE SECRETA
    x_admin_key: str = Header(None) 
    # =============================================================
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    file_path = None
    if file:
        # Lógica para guardar archivo temporal y anonimizar
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        file_path = anonymize_file(temp_path)

    # Nota: Tu modelo 'Case' requiere un 'title'.
    case_title = description[:50] if description else f"Caso Voluntario {user_id}-{datetime.datetime.utcnow().timestamp()}"
    
    payment_session_data = None
    case_status = "awaiting_payment" # Nuevo estado inicial para el flujo de pago

    # 1. VERIFICACIÓN DE ACCESO GRATUITO/ILIMITADO
    if x_admin_key and x_admin_key == ADMIN_BYPASS_KEY:
        # Admin: Acceso inmediato. El caso se marca como pagado y se analiza inmediatamente.
        case_status = "paid" # Marcamos como pagado
        ai_result = "PENDIENTE DE PROCESAMIENTO INMEDIATO (ADMIN)"
        print(f"ADMIN BYPASS ACTIVO: {user.email} obtiene acceso ilimitado.")
    else:
        # Usuario normal: Crear sesión de pago y mantener estado 'awaiting_payment'
        try:
            payment_session_data = create_volunteer_payment_session(
                user_email=user.email, 
                case_price=50,
                # CRUCIAL: Añadir metadatos para que el Webhook sepa qué caso actualizar
                metadata={"user_id": user_id, "description": description}
            )
            if "error" in payment_session_data:
                raise Exception(payment_session_data["error"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error en la creación de la sesión de pago: {str(e)}")

    # 2. Guardar Caso en DB
    new_case = Case(
        user_id=user_id,
        title=case_title,
        description=description,
        file_path=file_path,
        status=case_status, # 'paid' (admin) o 'awaiting_payment' (usuario)
        ai_result=ai_result if 'ai_result' in locals() else None, # Solo si es admin bypass
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 3. SI ES ADMIN, PROCESAR EL CASO INMEDIATAMENTE
    if is_admin_bypass:
        from services.ai_service import analyze_case # Importamos aquí para evitar ciclos
        try:
            ai_result = analyze_case(description, file_path)
            new_case.ai_result = ai_result
            new_case.status = "analyzed"
            db.commit()
            return {
                "message": "Caso enviado y analizado (ACCESO ILIMITADO)",
                "case_id": new_case.id,
                "ai_result": ai_result,
            }
        except Exception as e:
            new_case.status = "error"
            db.commit()
            raise HTTPException(status_code=500, detail=f"Error al analizar el caso: {str(e)}")


    # 4. Respuesta para USUARIO NORMAL (Requiere pago)
    return {
        "message": "Caso enviado. Pago requerido para el análisis.",
        "case_id": new_case.id,
        "payment_url": payment_session_data["url"]
    }
# ... (la ruta /my-cases/{user_id} se mantiene igual)
