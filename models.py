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
    submitted_cases = relationship("Case", foreign_keys="Case.volunteer_id", back_populates="owner")
    assigned_cases = relationship("Case", foreign_keys="Case.assigned_to_id")


# =================================================================
# Tabla para definir los planes de suscripción para profesionales
# =================================================================
class ProfessionalLevel(Base):
    __tablename__ = "professional_levels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    price_id = Column(String, unique=True, nullable=False)
    monthly_fee = Column(Float, nullable=False)
    features = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# =================================================================
# Casos clínicos
# =================================================================
class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    level = Column(String, default="basic")
    
    file_path = Column(String, nullable=True)
    ai_result = Column(Text, nullable=True)
    
    status = Column(String, default="pending") 
    
    stripe_session_id = Column(String, unique=True, index=True, nullable=True)
    is_paid = Column(Boolean, default=False)
    has_legal_consent = Column(Boolean, default=False)
    
    volunteer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", foreign_keys=[volunteer_id], back_populates="submitted_cases")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], viewonly=True)
