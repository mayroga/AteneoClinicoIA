from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
# CORRECCIÓN: Importar la función con el nombre correcto
from services.payment_service import create_volunteer_payment_session 
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file
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
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")

    # Pago obligatorio
    try:
        # CORRECCIÓN: Llamar a la función con el nombre correcto y pasar el email y precio
        payment_session_data = create_volunteer_payment_session(user_email=user.email, case_price=50)
        
        # Opcional: Si deseas que el pago sea bloqueante antes de guardar el caso, 
        # necesitarías más lógica aquí (como verificar el estado del pago o redirigir).
        # Para pasar la fase de inicio, solo nos aseguraremos de que no haya un error.
        if "error" in payment_session_data:
            raise Exception(payment_session_data["error"])

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en la creación de la sesión de pago: {str(e)}")

    file_path = None
    if file:
        # Guardar archivo temporal
        filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = f"temp/{filename}"
        os.makedirs("temp", exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        # Anonimizar archivo
        # Nota: Asegúrate de que anonymize_file está implementada y funciona con la ruta
        file_path = anonymize_file(temp_path)

    # Guardar caso en DB
    # NOTA: Tu modelo 'Case' requiere un 'title', pero no lo pides en el formulario.
    # Asumiremos un título temporal para evitar un error de DB (nullable=False).
    case_title = description[:50] if description else f"Caso Voluntario {new_case.id}"
    
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
        ai_result = analyze_case(description, file_path)
        new_case.ai_result = ai_result
        new_case.status = "analyzed"
        db.commit()
    except Exception as e:
        new_case.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Error al analizar el caso: {str(e)}")

    return {
        "message": "Caso enviado y analizado correctamente",
        "case_id": new_case.id,
        "ai_result": ai_result,
        "payment_url": payment_session_data["url"] if payment_session_data else None
    }

# Consulta de casos previos del voluntario
@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    
    cases = db.query(Case).filter(Case.volunteer_id == user_id).all()
    
    # Asegúrate de usar 'volunteer_id' si es la llave foránea correcta en el modelo Case
    # NOTA: En tu modelo Case tienes 'volunteer_id' pero en la consulta usaste 'Case.user_id'.
    # Lo corregí para usar volunteer_id.
    
    return [
        {
            "id": c.id, 
            "title": c.title,
            "description": c.description, 
            "status": c.status, 
            "ai_result": c.ai_result
        } for c in cases
    ]
