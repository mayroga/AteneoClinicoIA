from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from database import Base # Importamos la base declarativa
from typing import Optional

# =================================================================
# 1. Modelo User (Para Autenticación JWT)
# =================================================================

class User(Base):
    """Modelo para almacenar la información de los usuarios."""
    __tablename__ = "users"

    # ID primario, usando UUID para seguridad
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Opcional: Rol o nombre
    full_name = Column(String, nullable=True)

    # Opcional: Fecha de creación
    created_at = Column(DateTime, server_default=func.now())
    
    # Método de representación para depuración
    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}')>"

# =================================================================
# 2. Modelo Case (Para Casos Clínicos y Stripe)
# =================================================================

class Case(Base):
    """Modelo para almacenar los casos clínicos."""
    __tablename__ = "cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False) # Se relaciona con el usuario que lo subió
    
    # Campo para la lógica del pago y Stripe
    stripe_session_id = Column(String, unique=True, index=True, nullable=True) # ID de la sesión de Stripe
    is_paid = Column(Boolean, default=False) # Indica si el pago se ha completado
    
    # Campos del caso
    description = Column(Text, nullable=False)
    file_path = Column(String, nullable=True) # Ruta del archivo adjunto (e.g., PDF, imagen)
    ai_result = Column(Text, nullable=True) # El resultado del análisis de la IA
    
    # El campo de consentimiento legal (como se solicitó)
    has_legal_consent = Column(Boolean, default=False) 
    
    # Campos de estado y tiempo
    is_processed = Column(Boolean, default=False) # Indica si el caso ha sido procesado por la IA
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Case(id='{self.id}', paid={self.is_paid}, processed={self.is_processed})>"
