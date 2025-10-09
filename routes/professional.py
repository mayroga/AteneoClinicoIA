from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User, ProfessionalLevel
from services.ai_service import analyze_case
from services.anonymizer import anonymize_file
from datetime import datetime
import uuid
import os

router = APIRouter(prefix="/professional", tags=["professional"])

# Subida de caso clínico por profesional
@router.post("/submit-case")
async def submit_case(
    user_id: int = Form(...),
    description: str = Form(...),
    level: int = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.role.in_(["professional", "researcher"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es profesional")

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
        level=level,
        created_at=datetime.utcnow()
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
        "message": "Caso profesional enviado y analizado correctamente",
        "case_id": new_case.id,
        "ai_result": ai_result
    }

# Asignación de casos pendientes según nivel del profesional
@router.get("/assign-case/{user_id}")
def assign_case(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id, User.role.in_(["professional", "researcher"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no es profesional")

    # Obtener nivel del profesional
    level = db.query(ProfessionalLevel).filter(ProfessionalLevel.user_id == user_id).first()
    if not level:
        raise HTTPException(status_code=404, detail="Nivel profesional no asignado")

    # Buscar un caso pendiente que coincida con su nivel
    case = db.query(Case).filter(Case.status == "analyzed", Case.level <= level.level).first()
    if not case:
        return {"message": "No hay casos disponibles en este momento"}

    return {
        "case_id": case.id,
        "description": case.description,
        "ai_result": case.ai_result,
        "file_path": case.file_path
    }

# Ranking de profesionales por correcciones o participación
@router.get("/ranking")
def ranking(db: Session = Depends(get_db)):
    professionals = db.query(User).filter(User.role.in_(["professional", "researcher"])).all()
    ranking_list = []
    for prof in professionals:
        corrected_cases = db.query(Case).filter(Case.corrected_by == prof.id).count()
        ranking_list.append({"user_id": prof.id, "name": prof.name, "corrected_cases": corrected_cases})
    ranking_list.sort(key=lambda x: x["corrected_cases"], reverse=True)
    return ranking_list
