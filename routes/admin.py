from fastapi import APIRouter, Header, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Case, User
from config import ADMIN_BYPASS_KEY
from typing import List

router = APIRouter(prefix="/admin", tags=["admin"])

# --- DEPENDENCIA DE AUTENTICACIÓN ADMIN ---
async def admin_required(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_BYPASS_KEY:
        raise HTTPException(status_code=403, detail="Acceso Prohibido: Clave de Administrador incorrecta.")
    return True

# ------------------------------------------------------------------
# --- ENDPOINTS DE ADMINISTRACIÓN ---
# ------------------------------------------------------------------

@router.get("/users", response_model=List[dict], dependencies=[Depends(admin_required)])
def list_users(db: Session = Depends(get_db)):
    """Lista todos los usuarios (requiere clave de admin)."""
    users = db.query(User).all()
    # Retorna un formato simple (deberías usar Pydantic Models)
    return [{"id": u.id, "email": u.email, "role": u.role} for u in users]

@router.get("/cases", response_model=List[dict], dependencies=[Depends(admin_required)])
def list_cases(db: Session = Depends(get_db)):
    """Lista todos los casos (requiere clave de admin)."""
    cases = db.query(Case).all()
    return [{"id": c.id, "title": c.title, "status": c.status, "paid": c.is_paid} for c in cases]
