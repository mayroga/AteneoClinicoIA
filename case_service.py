from datetime import datetime
from database import db_session
from models import Case, User
from user_service import can_submit_case

# Crear un nuevo caso clínico
def create_case(user: User, title: str, description: str, media_files: list):
    """
    Crea un caso clínico para voluntarios.
    media_files es una lista de URLs o paths de archivos subidos.
    """
    if not can_submit_case(user):
        raise ValueError("Límite de casos alcanzado para este mes")

    case = Case(
        title=title,
        description=description,
        media_files=media_files,
        created_by=user.id,
        status="active",
        created_at=datetime.utcnow()
    )
    db_session.add(case)
    db_session.commit()
    return case

# Asignar caso a profesional
def assign_case(case: Case, professional: User):
    if professional.role.name.startswith("level") and can_submit_case(professional):
        case.assigned_to = professional.id
        case.assigned_at = datetime.utcnow()
        db_session.commit()
        return True
    return False

# Actualizar estado del caso
def update_case_status(case: Case, status: str):
    """
    status puede ser: active, completed, canceled, reviewed
    """
    case.status = status
    case.updated_at = datetime.utcnow()
    db_session.commit()
    return case

# Obtener casos activos de un usuario
def get_active_cases(user: User):
    return db_session.query(Case).filter_by(status="active", created_by=user.id).all()

# Obtener historial de casos asignados a un profesional
def get_assigned_cases(professional: User):
    return db_session.query(Case).filter_by(assigned_to=professional.id).all()
