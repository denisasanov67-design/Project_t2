# backend/app/main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime
from typing import List

# Импорты из локальных модулей
from app import models, schemas, auth, crud
from app.database import engine, get_db

# Создаем таблицы
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hackathon T2 - Shift Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Hackathon T2 API is running!"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- АВТОРИЗАЦИЯ ---
@app.post("/token", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}

# --- ИНИЦИАЛИЗАЦИЯ ТЕСТОВЫХ ДАННЫХ ---
@app.post("/api/init-test-data")
async def init_test_data(db: Session = Depends(get_db)):
    """Создает тестовые данные для демонстрации"""
    
    # Проверяем, есть ли уже данные
    existing_users = db.query(models.User).count()
    if existing_users > 0:
        return {"status": "warning", "message": "Данные уже существуют"}
    
    # Создаем организацию
    org = models.Organization(name="ООО Хакатон")
    db.add(org)
    db.flush()
    
    # Создаем альянсы и группы
    alliances_data = {
        "Пупкина": ["Группа Сизых", "Группа Василькова", "Группа Петькова", "Группа Ивановых"],
        "Тумбочкина": ["Группа Кузнецовых", "Группа Смирновых", "Группа Поповых", "Группа Волковых"],
    }
    
    employees_data = {
        "Группа Сизых": ["Сизый Александр Петрович", "Сизый Мария Ивановна"],
        "Группа Василькова": ["Васильков Иван Сергеевич", "Василькова Ольга Васильевна"],
        "Группа Петькова": ["Петьков Дмитрий Алексеевич", "Петькова Елена Дмитриевна"],
        "Группа Ивановых": ["Ивановых Николай Петрович", "Ивановых Анна Николаевна"],
        "Группа Кузнецовых": ["Кузнецов Виктор Михайлович", "Кузнецова Светлана Викторовна"],
        "Группа Смирновых": ["Смирновых Алексей Иванович", "Смирновых Наталья Алексеевна"],
    }
    
    for alliance_name, groups in alliances_data.items():
        alliance = models.Alliance(name=alliance_name, organization_id=org.id)
        db.add(alliance)
        db.flush()
        
        for group_name in groups:
            group = models.Group(name=group_name, alliance_id=alliance.id)
            db.add(group)
            db.flush()
            
            if group_name in employees_data:
                for emp_name in employees_data[group_name]:
                    employee = models.Employee(full_name=emp_name, group_id=group.id)
                    db.add(employee)
    
    # Создаем тестовых пользователей
    users_data = [
        {"username": "admin", "password": "admin123", "role": "admin"},
        {"username": "manager", "password": "manager123", "role": "manager"},
        {"username": "employee", "password": "employee123", "role": "employee"},
    ]
    
    for user_data in users_data:
        user = models.User(
            username=user_data["username"],
            hashed_password=auth.get_password_hash(user_data["password"]),
            role=user_data["role"]
        )
        db.add(user)
    
    db.commit()
    
    return {"status": "success", "message": "Тестовые данные созданы", "users": users_data}

# --- ПОЛУЧЕНИЕ ДАННЫХ ---
@app.get("/api/init-data")
async def get_init_data(db: Session = Depends(get_db)):
    """Возвращает все альянсы, группы и сотрудников"""
    alliances = db.query(models.Alliance).all()
    
    result = {}
    for alliance in alliances:
        result[alliance.name] = []
        for group in alliance.groups:
            employees = [emp.full_name for emp in group.employees]
            result[alliance.name].append({
                "name": group.name,
                "employees": employees
            })
    
    return result

@app.get("/api/employees")
async def get_employees(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Получает всех сотрудников с их сменами"""
    if current_user.role == "employee" and current_user.employee:
        employees = [current_user.employee]
    else:
        employees = db.query(models.Employee).all()
    
    result = []
    for emp in employees:
        emp_data = {
            "id": emp.id,
            "name": emp.full_name,
            "alliance": emp.group.alliance.name if emp.group and emp.group.alliance else "",
            "group": emp.group.name if emp.group else "",
            "shifts": [
                {
                    "id": shift.id,
                    "date": shift.date.isoformat() if shift.date else "",
                    "startTime": shift.start_time,
                    "endTime": shift.end_time,
                    "status": shift.status
                }
                for shift in emp.shifts
            ]
        }
        result.append(emp_data)
    
    return result