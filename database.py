from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from models import Base # <--- CORRECCIÓN CLAVE: Importa Base desde models.py

# Asumimos que la URL de la DB está en una variable de entorno de Render
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./ateneo_test.db")

# Corrección de la URL para PostgreSQL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
