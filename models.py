from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# Usuarios (voluntarios y profesionales)
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String, nullable=False)  # volunteer, clinician
    created_at = Column(DateTime, default=datetime.utcnow)

    cases = relationship("Case", back_populates="owner")
    # Nota: También podrías añadir una relación para 'assigned_cases' si fuera necesario
    # assigned_cases = relationship("Case", foreign_keys='Case.assigned_to_id', viewonly=True)

# Tabla para definir los planes de suscripción para profesionales (LA CLASE FALTANTE)
class ProfessionalLevel(Base):
    __tablename__ = "professional_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # E.g., "Nivel 1 Básico"
    price_id = Column(String, unique=True, nullable=False) # ID del producto en Stripe para facturación
    monthly_fee = Column(Float, nullable=False) # Cuota mensual en USD
    features = Column(Text, nullable=True) # Descripción de las características del plan
    created_at = Column(DateTime, default=datetime.utcnow)

# Casos clínicos
class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    level = Column(String, default="basic")  # basic, medium, advanced
    status = Column(String, default="pending")  # pending, in_progress, completed
    volunteer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", foreign_keys=[volunteer_id], back_populates="cases")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
