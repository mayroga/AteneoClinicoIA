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
