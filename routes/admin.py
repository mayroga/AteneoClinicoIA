from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from database import get_db
from models import User, Case # Asegúrate de que Case y User se importen desde models
from services.payment_service import get_all_payments
from config import ADMIN_BYPASS_KEY
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])

# ------------------------------------------------------------------
# 🔑 Dependencia para validar acceso de administrador (Developer Bypass)
# ------------------------------------------------------------------
def admin_required(x_admin_key: str = Header(...)):
    """
    Verifica si el encabezado X-Admin-Key coincide con el ADMIN_BYPASS_KEY
    configurado en las variables de entorno de Render.
    """
    if x_admin_key != ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado: clave administrativa inválida")
    return True

# ------------------------------------------------------------------
# 1. Obtener lista de todos los usuarios
# ------------------------------------------------------------------
@router.get("/users")
def get_users(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    users = db.query(User).all()
    # NOTA: Se asume que User tiene un campo 'name' para el retorno.
    return [
        {
            "id": u.id, 
            "email": u.email, 
            "role": u.role,
            "created_at": u.created_at
        } for u in users
    ]

# ------------------------------------------------------------------
# 2. Obtener lista de todos los casos (Corregido: volunteer_id y campos)
# ------------------------------------------------------------------
@router.get("/cases")
def get_cases(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    cases = db.query(Case).all()
    return [
        {
            "id": c.id,
            "volunteer_id": c.volunteer_id, # 🔑 CORREGIDO: Usar volunteer_id
            "title": c.title,
            "description": c.description,
            "status": c.status,
            "is_paid": c.is_paid, # Campo importante para Stripe
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "ai_result": c.ai_result,
        } for c in cases
    ]

# ------------------------------------------------------------------
# 3. Revisar pagos recibidos a través de Stripe
# ------------------------------------------------------------------
@router.get("/payments")
def payments(admin: bool = Depends(admin_required)):
    try:
        # Llama a la función de servicio que interactúa con la API de Stripe
        payments_list = get_all_payments()
        if "error" in payments_list:
             raise Exception(payments_list["error"])
        return payments_list
    except Exception as e:
        # Esto atrapará errores de conexión o configuración de Stripe
        raise HTTPException(status_code=500, detail=f"Error al obtener pagos de Stripe: {str(e)}")

# ------------------------------------------------------------------
# 4. Estadísticas generales de la plataforma
# ------------------------------------------------------------------
@router.get("/stats")
def stats(admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_cases = db.query(Case).count()
    cases_completed = db.query(Case).filter(Case.status == "completed").count() # Usamos 'completed' de volunteer.py
    cases_pending = db.query(Case).filter(Case.status.in_(["pending", "awaiting_payment", "processing"])).count()
    
    return {
        "total_users": total_users,
        "total_cases": total_cases,
        "cases_completed": cases_completed,
        "cases_pending_or_processing": cases_pending
    }

# ------------------------------------------------------------------
# 5. Actualización manual de estado de un caso (CORREGIDO Y COMPLETADO)
# ------------------------------------------------------------------
@router.put("/update-case/{case_id}")
def update_case(case_id: int, status: str, admin: bool = Depends(admin_required), db: Session = Depends(get_db)):
    # 1. Buscar el caso
    case = db.query(Case).filter(Case.id == case_id).first()
    
    if not case:
        raise HTTPException(status_code=404, detail=f"Caso con ID {case_id} no encontrado.")
        
    # 2. Validar el nuevo estado (opcional: lista de estados válidos)
    valid_statuses = ["pending", "processing", "completed", "error", "archived", "paid"]
    if status.lower() not in valid_statuses:
         raise HTTPException(status_code=400, detail=f"Estado inválido. Use uno de: {', '.join(valid_statuses)}")

    # 3. Actualizar
    case.status = status.lower()
    case.updated_at = datetime.utcnow()
    
    # 4. Guardar
    try:
        db.commit()
        db.refresh(case)
        return {"message": f"Estado del caso {case_id} actualizado a '{status}'.", "case_id": case.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar la DB: {str(e)}")
