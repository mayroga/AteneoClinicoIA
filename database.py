from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

# Motor de la base de datos
# pool_pre_ping=True ayuda a asegurarse de que la conexión es válida
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Sesión de conexión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()

# --- FUNCIÓN AÑADIDA PARA INICIALIZAR LA BASE DE DATOS ---
def init_db():
    """
    Crea las tablas de la base de datos a partir de los modelos
    que heredan de Base.
    """
    # IMPORTANTE: Asegúrate de importar tu(s) archivo(s) de modelos (e.g., import models)
    # antes de llamar a create_all para que Base.metadata los conozca.
    # Si tus modelos están en un archivo 'models.py', deberías importarlos aquí.
    
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
