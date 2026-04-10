# backend/main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime
from typing import List

# Импорты из папки app
from app.database import engine, get_db
from app import models, schemas, auth

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
        return {"status": "warning", "message": "Данные уже существуют", "count": existing_users}
    
    try:
        # Создаем организацию
        org = models.Organization(name="ООО Хакатон")
        db.add(org)
        db.flush()
        
        # Создаем альянсы и группы
        alliances_data = {
            "Пупкина": ["Группа Сизых", "Группа Василькова", "Группа Петькова", "Группа Ивановых"],
            "Тумбочкина": ["Группа Кузнецовых", "Группа Смирновых", "Группа Поповых", "Группа Волковых"],
            "Петровича": ["Группа Морозовых", "Группа Лебедевых", "Группа Козловых", "Группа Соболевых"],
            "Сидоровича": ["Группа Никифоровых", "Группа Поляковых", "Группа Савельевых", "Группа Тарасовых"]
        }
        
        employees_data = {
            "Группа Сизых": ["Сизый Александр Петрович", "Сизый Мария Ивановна"],
            "Группа Василькова": ["Васильков Иван Сергеевич", "Василькова Ольга Васильевна"],
            "Группа Петькова": ["Петьков Дмитрий Алексеевич", "Петькова Елена Дмитриевна"],
            "Группа Ивановых": ["Ивановых Николай Петрович", "Ивановых Анна Николаевна"],
            "Группа Кузнецовых": ["Кузнецов Виктор Михайлович", "Кузнецова Светлана Викторовна"],
            "Группа Смирновых": ["Смирновых Алексей Иванович", "Смирновых Наталья Алексеевна"],
            "Группа Поповых": ["Поповых Евгений Сергеевич", "Поповых Ирина Евгеньевна"],
            "Группа Волковых": ["Волковых Павел Дмитриевич", "Волкова Екатерина Павловна"],
            "Группа Морозовых": ["Морозовых Андрей Владимирович", "Морозова Ольга Андреевна"],
            "Группа Лебедевых": ["Лебедевых Сергей Николаевич", "Лебедева Мария Сергеевна"],
            "Группа Козловых": ["Козловых Дмитрий Юрьевич", "Козлова Анна Дмитриевна"],
            "Группа Соболевых": ["Соболевых Иван Петрович", "Соболева Елена Ивановна"],
            "Группа Никифоровых": ["Никифоровых Роман Александрович", "Никифорова Татьяна Романовна"],
            "Группа Поляковых": ["Поляковых Михаил Васильевич", "Полякова Ирина Михайловна"],
            "Группа Савельевых": ["Савельевых Алексей Константинович", "Савельева Надежда Алексеевна"],
            "Группа Тарасовых": ["Тарасовых Владимир Сергеевич", "Тарасова Ольга Владимировна"]
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
        
        return {
            "status": "success", 
            "message": "Тестовые данные созданы",
            "users": [{"username": u["username"], "password": u["password"], "role": u["role"]} for u in users_data]
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}

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
    if current_user.role == "employee":
        # Сотрудник видит только себя
        if current_user.employee:
            employees = [current_user.employee]
        else:
            employees = []
    else:
        # Руководитель/админ видят всех
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

# --- РАБОТА СО СМЕНАМИ ---
@app.post("/api/shifts")
async def add_shift(
    employee_id: int,
    shift_data: schemas.ShiftCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Добавление новой смены"""
    # Проверка прав
    if current_user.role == "employee":
        if not current_user.employee or current_user.employee.id != employee_id:
            raise HTTPException(status_code=403, detail="Cannot add shifts for other employees")
    
    # Проверяем сотрудника
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Создание смены
    new_shift = models.Shift(
        employee_id=employee_id,
        date=shift_data.date,
        start_time=shift_data.start_time,
        end_time=shift_data.end_time,
        status="pending"
    )
    
    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)
    
    return {"status": "success", "shift_id": new_shift.id}

@app.delete("/api/shifts/{shift_id}")
async def delete_shift(
    shift_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Удаление смены"""
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    # Проверка прав
    if current_user.role == "employee":
        if not shift.employee.user_id or shift.employee.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Cannot delete this shift")
    
    db.delete(shift)
    db.commit()
    
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)