from sqlalchemy.orm import Session
from app import models
from app import schemas
from datetime import datetime

def get_employee(db: Session, employee_id: int):
    return db.query(models.Employee).filter(models.Employee.id == employee_id).first()

def get_employee_by_name(db: Session, full_name: str, group_name: str, alliance_name: str):
    return db.query(models.Employee).join(models.Group).join(models.Alliance).filter(
        models.Employee.full_name == full_name,
        models.Group.name == group_name,
        models.Alliance.name == alliance_name
    ).first()

def get_employees(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Employee).offset(skip).limit(limit).all()

def create_employee(db: Session, employee: schemas.EmployeeCreate):
    # Находим или создаем альянс
    alliance = db.query(models.Alliance).filter(
        models.Alliance.name == employee.alliance_name
    ).first()
    if not alliance:
        alliance = models.Alliance(name=employee.alliance_name)
        db.add(alliance)
        db.flush()
    
    # Находим или создаем группу
    group = db.query(models.Group).filter(
        models.Group.name == employee.group_name,
        models.Group.alliance_id == alliance.id
    ).first()
    if not group:
        group = models.Group(name=employee.group_name, alliance_id=alliance.id)
        db.add(group)
        db.flush()
    
    # Создаем сотрудника
    db_employee = models.Employee(
        full_name=employee.full_name,
        group_id=group.id
    )
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def create_shift(db: Session, shift: schemas.ShiftCreate, employee_id: int):
    db_shift = models.Shift(
        employee_id=employee_id,
        date=shift.date,
        start_time=shift.start_time,
        end_time=shift.end_time,
        status="pending"
    )
    db.add(db_shift)
    db.commit()
    db.refresh(db_shift)
    return db_shift

def get_shifts_by_employee(db: Session, employee_id: int):
    return db.query(models.Shift).filter(models.Shift.employee_id == employee_id).all()

def delete_shift(db: Session, shift_id: int):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if shift:
        db.delete(shift)
        db.commit()
    return shift

def approve_shift(db: Session, shift_id: int, approved_by: int):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if shift:
        shift.status = "approved"
        shift.approved_by = approved_by
        shift.approved_at = datetime.utcnow()
        db.commit()
    return shift