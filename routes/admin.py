from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import User, Case
from services.payment_service import get_all_payments
from config import ADMIN_BYPASS_KEY
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])

# Dependencia para validar acceso de administrador
def admin_required(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado: clave administrativa inválida")
    return True

# Obtener lista de todos los usuarios
@router.get("/users")
def get_users(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in users]

# Obtener lista de todos los casos
@router.get("/cases")
def get_cases(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    cases = db.query(Case).all()
    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "description": c.description,
            "status": c.status,
            "level": c.level,
            "created_at": c.created_at,
            "ai_result": c.ai_result,
            "corrected_by": c.corrected_by
        } for c in cases
    ]

# Revisar pagos recibidos
@router.get("/payments")
def payments(admin: bool = Depends(admin_required)):
    try:
        payments_list = get_all_payments()
        return payments_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pagos: {str(e)}")

# Estadísticas generales de la plataforma
@router.get("/stats")
def stats(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_cases = db.query(Case).count()
    cases_analyzed = db.query(Case).filter(Case.status == "analyzed").count()
    cases_pending = db.query(Case).filter(Case.status == "pending").count()
    return {
        "total_users": total_users,
        "total_cases": total_cases,
        "cases_analyzed": cases_analyzed,
        "cases_pending": cases_pending
    }

# Actualización manual de estado de un caso
@router.put("/update-case/{case_id}")
def update_case(case_id: int, status: str, admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Caso no encontrado")
    case.status = status
    db.commit()
    return {"message": f"Caso {case_id} actualizado a estado '{status}'"}
