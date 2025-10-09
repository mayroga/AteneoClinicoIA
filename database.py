from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
# Eliminado: import models # Se mueve dentro de init_db para evitar circular imports

# Motor de la base de datos
# pool_pre_ping=True ayuda a asegurarse de que la conexión es válida
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Sesión de conexión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()

# --- FUNCIÓN CORREGIDA PARA INICIALIZAR LA BASE DE DATOS ---
def init_db():
    """
    Crea las tablas de la base de datos a partir de los modelos
    que heredan de Base, asegurando que todos los modelos han sido cargados.
    """
    try:
        # Importamos los modelos justo antes de usarlos. Esto rompe la dependencia circular
        # porque la importación solo ocurre cuando se llama a esta función (en el lifespan),
        # y no cuando Python carga el módulo 'database'.
        import models 
    except ImportError:
        # Esto es solo si el archivo models.py no existe o está mal nombrado
        print("Warning: Could not import models. Check file name and location.")
        pass

    print("Attempting to create database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database initialization successful.")
# --------------------------------------------------------

# Dependencia para obtener sesión DB
def get_db():
    """Proporciona una sesión de base de datos para las dependencias de FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
