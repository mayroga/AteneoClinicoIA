from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base # Asume que 'database.py' define la clase Base

# =================================================================
# Usuarios (voluntarios y profesionales)
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

    # Relación: Un usuario puede ser dueño (voluntario/profesional) de muchos casos
    cases = relationship("Case", foreign_keys="Case.volunteer_id", back_populates="owner")
    # Relación: Un usuario (profesional) puede tener casos asignados
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
    level = Column(String, default="basic")  # basic, medium, advanced
    
    # 🔑 Campos del flujo de IA/Archivos 🔑
    file_path = Column(String, nullable=True)  # Ruta al archivo anonimizado
    ai_result = Column(Text, nullable=True)    # Resultado del análisis de la IA
    
    # Estados: pending, awaiting_payment, processing, completed, error
    status = Column(String, default="pending") 
    
    # 💳 CAMPOS AÑADIDOS PARA STRIPE Y CONSENTIMIENTO 💳
    stripe_session_id = Column(String, unique=True, index=True, nullable=True)
    is_paid = Column(Boolean, default=False)
    has_legal_consent = Column(Boolean, default=False)
    # --------------------------------------------------
    
    # Relaciones con User
    volunteer_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # El usuario que lo subió
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True) # El profesional asignado para revisión
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # Definición de relaciones ORM
    owner = relationship("User", foreign_keys=[volunteer_id], back_populates="cases")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], viewonly=True)
