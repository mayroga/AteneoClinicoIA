from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from config import DATABASE_URL
# >>> CORRECCIÓN: Eliminamos 'from models import Case' de aquí
# Esto rompe la dependencia circular.

# Motor de la base de datos
# pool_pre_ping=True ayuda a asegurarse de que la conexión es válida
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Sesión de conexión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos (declarative_base DEBE estar aquí)
Base = declarative_base()

# --- FUNCIÓN PARA INICIALIZAR LA BASE DE DATOS ---
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

# --- Dependencia para obtener sesión DB ---
def get_db():
    """Proporciona una sesión de base de datos para las dependencias de FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Funciones de Acceso a Datos (Añadidas para el Webhook) ---

def get_case_by_id(db: Session, case_id: str):
    """
    Busca un caso clínico por su case_id (UUID o identificador único).
    NOTA: La importación de Case se realiza dentro de la función para romper el ciclo de dependencia.
    """
    # >>> CORRECCIÓN: Importamos Case justo antes de usarlo.
    from models import Case 
    # Ya no se usa la anotación Case | None en la cabecera
    
    # Consulta la tabla Case filtrando por el ID
    return db.query(Case).filter(Case.id == case_id).first()
