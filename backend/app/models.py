from sqlalchemy import Column, Integer, String, ForeignKey, Date, Time, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    
    alliances = relationship("Alliance", back_populates="organization")

class Alliance(Base):
    __tablename__ = "alliances"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    
    organization = relationship("Organization", back_populates="alliances")
    groups = relationship("Group", back_populates="alliance")

class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    alliance_id = Column(Integer, ForeignKey("alliances.id"))
    
    alliance = relationship("Alliance", back_populates="groups")
    employees = relationship("Employee", back_populates="group")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # связь с пользователем системы
    
    group = relationship("Group", back_populates="employees")
    user = relationship("User", back_populates="employee")
    shifts = relationship("Shift", back_populates="employee")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="employee")  # employee, manager, admin
    is_active = Column(Boolean, default=True)
    
    employee = relationship("Employee", back_populates="user", uselist=False)
    approved_shifts = relationship("Shift", foreign_keys="Shift.approved_by")

class Shift(Base):
    __tablename__ = "shifts"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    date = Column(Date, index=True)
    start_time = Column(String)  # "09:00" или "Выходной"
    end_time = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, approved, rejected
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    employee = relationship("Employee", back_populates="shifts")