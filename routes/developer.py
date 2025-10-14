from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file
from config import ADMIN_BYPASS_KEY
import datetime
import uuid
import os

router = APIRouter(prefix="/dev", tags=["developer"], include_in_schema=False)

# Usamos un ID fijo (1) para simular el usuario admin/dev que usa esta ruta
# Asegúrate de que el usuario con ID 1 exista en tu base de datos de desarrollo.
DEV_USER_ID = 1

@router.post("/process-case-free")
async def process_case_free(
    description: str = Form(...),
    has_legal_consent: bool = Form(True), # Asumimos consentimiento para desarrollo
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    # Requiere la clave de administrador para acceder a este endpoint
    x_admin_key: str = Header(...)
):
    """
    Endpoint de acceso ilimitado y gratuito para desarrolladores/administradores.
    Procesa el caso inmediatamente con la IA, sin pasar por Stripe.
    """
    
    # 1. VERIFICACIÓN DE ACCESO DE ADMINISTRADOR (Clave saneada con .strip())
    # Esto previene errores de espacios en blanco al copiar y pegar la clave.
    if x_admin_key.strip() != ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado. Clave de administrador no válida.")

    # 2. Asignar a un usuario DEV fijo
    user = db.query(User).filter(User.id == DEV_USER_ID).first()
    if not user:
        raise HTTPException(status_code=500, detail=f"Usuario de desarrollo (ID {DEV_USER_ID}) no encontrado.")

    file_path = None
    ai_result = "PENDIENTE DE ANÁLISIS"

    # 3. Manejo y Anonimización del Archivo
    if file:
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        
        file_path = anonymize_file(temp_path)
    
    case_title = description[:50] if description else f"Caso DEV {user.email}-{datetime.datetime.utcnow().timestamp()}"

    # 4. Guardar Caso en DB
    new_case = Case(
        volunteer_id=DEV_USER_ID,
        title=case_title,
        description=description,
        file_path=file_path,
        status="processing", 
        is_paid=True, # Acceso gratuito implica pago completado
        has_legal_consent=has_legal_consent,
        created_at=datetime.datetime.utcnow(),
        stripe_session_id="DEV_BYPASS" # Marcador para indicar que no pasó por Stripe
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 5. Procesar el Caso Inmediatamente con la IA
    try:
        print(f"DEBUG: Ejecutando análisis de IA para caso {new_case.id} (DEV Bypass)")
        ai_result = analyze_case(description, file_path)
        
        new_case.ai_result = ai_result
        new_case.status = "completed"
        db.commit()
        
        return {
            "message": "Caso procesado con éxito (ACCESO GRATUITO ILIMITADO)",
            "case_id": new_case.id,
            "ai_result": ai_result,
            "status": "completed"
        }
        
    except Exception as e:
        # 6. Manejo de Errores de la IA
        print(f"ERROR IA: Fallo al analizar el caso de Dev {new_case.id}: {str(e)}")
        new_case.status = "error"
        new_case.ai_result = f"Error de procesamiento de IA: {str(e)}" 
        db.commit()
        
        raise HTTPException(
            status_code=500, 
            detail=f"Error al analizar el caso (Dev Bypass): {str(e)}"
        )
