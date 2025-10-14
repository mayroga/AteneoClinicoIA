from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from typing import Optional 
from config import DATABASE_URL

# Motor de la base de datos
# pool_pre_ping=True ayuda a asegurarse de que la conexión es válida
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Sesión de conexión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos (declarative_base DEBE estar aquí)
Base = declarative_base()

# ------------------------------------------------------------------
# --- FUNCIÓN PARA INICIALIZAR LA BASE DE DATOS ---
# ------------------------------------------------------------------
def init_db():
    """
    Crea las tablas de la base de datos a partir de los modelos
    que heredan de Base.
    """
    try:
        # Importamos models aquí para asegurar que las clases se carguen
        import models 
    except ImportError:
        print("Advertencia: No se pudieron importar los modelos. Comprueba el archivo models.py.")
        pass

    print("Intentando crear tablas de base de datos...")
    Base.metadata.create_all(bind=engine)
    print("Inicialización de base de datos exitosa.")

# ------------------------------------------------------------------
# --- Dependencia para obtener sesión DB ---
# ------------------------------------------------------------------
def get_db():
    """Proporciona una sesión de base de datos para las dependencias de FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------------------------------
# --- Funciones de Acceso a Datos (Añadidas para el Webhook y Auth) ---
# ------------------------------------------------------------------

def get_case_by_id(db: Session, case_id: str):
    """
    Busca un caso clínico por su case_id (UUID o identificador único).
    """
    # Importamos aquí para romper la dependencia circular
    from models import Case 
    return db.query(Case).filter(Case.id == case_id).first()

# 🔑 FUNCIÓN PARA EL DESBLOQUEO DE STRIPE
def get_case_by_stripe_session_id(db: Session, session_id: str) -> Optional:
    """
    Busca un caso clínico por el ID de la sesión de Stripe.
    Usada por el webhook para encontrar el caso después de un pago exitoso.
    """
    # Importamos aquí para romper la dependencia circular
    from models import Case 
    # Buscamos el primer caso que coincida con el ID de sesión
    return db.query(Case).filter(Case.stripe_session_id == session_id).first()


# 🔑 FUNCIÓN PARA EL DESBLOQUEO DE AUTH
def get_user_by_id(db: Session, user_id: str) -> Optional:
    """
    Busca un usuario por su ID.
    Usada por la dependencia de autenticación (FastAPI Security/JWT).
    """
    # Importamos aquí para romper la dependencia circular
    from models import User 
    # Buscamos el primer usuario que coincida con el ID
    return db.query(User).filter(User.id == user_id).first()
