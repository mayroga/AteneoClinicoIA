from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base() # <-- Define la Base aquí

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    full_name = Column(String, nullable=True)
    role = Column(String, default="volunteer") # "volunteer", "professional", "admin"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    cases = relationship("Case", back_populates="volunteer")

class Case(Base):
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True, index=True)
    volunteer_id = Column(Integer, ForeignKey("users.id"))
    
    title = Column(String)
    description = Column(Text)
    file_path = Column(String, nullable=True)
    
    status = Column(String, default="pending") 
    is_paid = Column(Boolean, default=False)
    price_paid = Column(Integer, default=50) 
    stripe_session_id = Column(String, nullable=True)
    has_legal_consent = Column(Boolean, default=False)

    ai_result = Column(Text, nullable=True) 

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    volunteer = relationship("User", back_populates="cases")
