from datetime import datetime, timedelta
from database import db_session
from models import User, Role, Case
from config import ADMIN_BYPASS_KEY

# Crear usuario
def create_user(email: str, role_name: str, bypass_key: str = None):
    """
    Crea un usuario nuevo con rol definido.
    bypass_key permite crear admins con acceso ilimitado.
    """
    if bypass_key == ADMIN_BYPASS_KEY:
        role_name = "admin"
    role = db_session.query(Role).filter_by(name=role_name).first()
    if not role:
        raise ValueError(f"Rol {role_name} no encontrado")
    
    user = User(email=email, role_id=role.id, created_at=datetime.utcnow())
    db_session.add(user)
    db_session.commit()
    return user

# Validar límites de participación
def can_submit_case(user: User):
    """
    Verifica si el usuario puede enviar un nuevo caso según su rol.
    """
    if user.role.name == "volunteer":
        active_cases = db_session.query(Case).filter_by(user_id=user.id, status="active").count()
        return active_cases < 2  # Máx 2 casos por mes
    elif user.role.name.startswith("professional"):
        # Profesionales tienen límites según nivel
        level_limits = {"level1": 5, "level2": 10, "level3": 15}
        active_cases = db_session.query(Case).filter_by(assigned_to=user.id, status="active").count()
        return active_cases < level_limits.get(user.role.name, 0)
    elif user.role.name == "admin":
        return True
    return False

# Obtener rol del usuario
def get_user_role(user_id: int):
    user = db_session.query(User).get(user_id)
    return user.role.name if user else None

# Actualizar último acceso
def update_last_access(user: User):
    user.last_access = datetime.utcnow()
    db_session.commit()
