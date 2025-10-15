from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base # Asume que 'database.py' define la clase Base

# =================================================================
# Usuarios (voluntarios, profesionales, admin)
# =================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String, nullable=False)  # volunteer, professional, admin
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relaciones:
    # Casos donde el usuario es el remitente (volunteer_id)
    submitted_cases = relationship("Case", foreign_keys="Case.volunteer_id", back_populates="owner")
    # Casos donde el usuario es el asignado (assigned_to_id)
    assigned_cases = relationship("Case", foreign_keys="Case.assigned_to_id")


# =================================================================
# Tabla para definir los planes de suscripción para profesionales
# =================================================================
class ProfessionalLevel(Base):
    __tablename__ = "professional_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False) # E.g., "Nivel 1 Básico"
    price_id = Column(String, unique=True, nullable=False) # ID del producto en Stripe para facturación
    monthly_fee = Column(Float, nullable=False) # Cuota mensual en USD
    features = Column(Text, nullable=True) # Descripción de las características del plan
    created_at = Column(DateTime, default=datetime.utcnow)

# =================================================================
# Casos clínicos (Actualizado)
# =================================================================
class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    level = Column(String, default="basic")
    
    # 🔑 Campos del flujo de IA/Archivos 🔑
    file_path = Column(String, nullable=True)
    ai_result = Column(Text, nullable=True)
    
    # Estados: pending, awaiting_payment, processing, completed, error
    status = Column(String, default="pending") 
    
    # 💳 CAMPOS PARA STRIPE Y CONSENTIMIENTO 💳
    stripe_session_id = Column(String, unique=True, index=True, nullable=True)
    is_paid = Column(Boolean, default=False)
    has_legal_consent = Column(Boolean, default=False)
    
    # Relaciones con User
    volunteer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Definición de relaciones ORM
    owner = relationship("User", foreign_keys=[volunteer_id], back_populates="submitted_cases")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], viewonly=True)
