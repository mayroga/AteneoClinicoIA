from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from services.payment_service import charge_volunteer
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
        charge_volunteer(user_id, amount=50)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en el pago: {str(e)}")

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

    # Guardar caso en DB
    new_case = Case(
        user_id=user_id,
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
        "ai_result": ai_result
    }

# Consulta de casos previos del voluntario
@router.get("/my-cases/{user_id}")
def my_cases(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role == "volunteer").first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es voluntario")
    
    cases = db.query(Case).filter(Case.user_id == user_id).all()
    return [{"id": c.id, "description": c.description, "status": c.status, "ai_result": c.ai_result} for c in cases]
