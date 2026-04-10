from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import date, timedelta
from typing import List
import models, schemas, auth, crud
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Hackathon T2 - Shift Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- АВТОРИЗАЦИЯ ---
@app.post("/token", response_model=schemas.Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role}

# --- ПОЛУЧЕНИЕ ДАННЫХ ДЛЯ ФРОНТЕНДА ---
@app.get("/api/init-data")
async def get_init_data(db: Session = Depends(get_db)):
    """Возвращает все альянсы, группы и сотрудников для заполнения select'ов"""
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
        # Сотрудник видит только себя
        employees = [current_user.employee]
    else:
        # Руководитель/админ видят всех
        employees = db.query(models.Employee).all()
    
    result = []
    for emp in employees:
        emp_data = {
            "id": emp.id,
            "name": emp.full_name,
            "alliance": emp.group.alliance.name,
            "group": emp.group.name,
            "shifts": [
                {
                    "id": shift.id,
                    "date": shift.date.isoformat(),
                    "startTime": shift.start_time,
                    "endTime": shift.end_time,
                    "status": shift.status
                }
                for shift in emp.shifts
            ]
        }
        result.append(emp_data)
    
    return result

@app.post("/api/shifts")
async def add_shift(
    shift_data: schemas.ShiftCreate,
    employee_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """Добавление новой смены"""
    # Проверка прав
    if current_user.role == "employee" and current_user.employee.id != employee_id:
        raise HTTPException(status_code=403, detail="Cannot add shifts for other employees")
    
    # Проверка на 6 смен подряд
    employee = db.query(models.Employee).filter(models.Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Логика проверки последовательных смен
    existing_shifts = db.query(models.Shift).filter(
        models.Shift.employee_id == employee_id,
        models.Shift.date >= shift_data.date - timedelta(days=6),
        models.Shift.date <= shift_data.date + timedelta(days=6)
    ).order_by(models.Shift.date).all()
    
    # Проверка на 6 подряд (упрощенно)
    consecutive_count = 1
    current_date = shift_data.date
    for shift in existing_shifts:
        if abs((shift.date - current_date).days) == 1:
            consecutive_count += 1
            current_date = shift.date
    
    if consecutive_count > 6:
        raise HTTPException(status_code=400, detail="Превышен лимит в 6 смен подряд")
    
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
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    # Проверка прав
    if current_user.role == "employee" and shift.employee.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete this shift")
    
    db.delete(shift)
    db.commit()
    
    return {"status": "success"}

@app.patch("/api/shifts/{shift_id}/approve")
async def approve_shift(
    shift_id: int,
    current_user: models.User = Depends(auth.get_current_requiring_role("manager")),
    db: Session = Depends(get_db)
):
    """Подтверждение смены руководителем (план/факт)"""
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    
    shift.status = "approved"
    shift.approved_by = current_user.id
    shift.approved_at = datetime.utcnow()
    
    db.commit()
    return {"status": "approved"}

# --- ВЫГРУЗКА ---
@app.get("/api/export/csv")
async def export_csv(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    import csv
    from io import StringIO
    
    # Получаем данные в зависимости от роли
    if current_user.role == "employee":
        shifts = db.query(models.Shift).filter(
            models.Shift.employee.has(user_id=current_user.id)
        ).all()
    else:
        shifts = db.query(models.Shift).all()
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Сотрудник', 'Альянс', 'Группа', 'Дата', 'Начало', 'Конец', 'Статус'])
    
    for shift in shifts:
        writer.writerow([
            shift.employee.full_name,
            shift.employee.group.alliance.name,
            shift.employee.group.name,
            shift.date,
            shift.start_time,
            shift.end_time or '',
            shift.status
        ])
    
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=schedule_export.csv"}
    )

# --- ИНИЦИАЛИЗАЦИЯ ТЕСТОВЫХ ДАННЫХ ---
@app.post("/api/init-test-data")
async def init_test_data(db: Session = Depends(get_db)):
    """Создает тестовые данные для демонстрации"""
    # Создаем организацию
    org = models.Organization(name="ООО Хакатон")
    db.add(org)
    db.flush()
    
    # Создаем альянсы
    alliances_data = {
        "Пупкина": ["Группа Сизых", "Группа Василькова", "Группа Петькова", "Группа Ивановых"],
        "Тумбочкина": ["Группа Кузнецовых", "Группа Смирновых", "Группа Поповых", "Группа Волковых"],
        "Петровича": ["Группа Морозовых", "Группа Лебедевых", "Группа Козловых", "Группа Соболевых"],
        "Сидоровича": ["Группа Никифоровых", "Группа Поляковых", "Группа Савельевых", "Группа Тарасовых"]
    }
    
    employees_data = {
        "Группа Сизых": ["Сизый Александр Петрович", "Сизый Мария Ивановна"],
        "Группа Василькова": ["Васильков Иван Сергеевич", "Василькова Ольга Васильевна"],
        # ... остальные группы
    }
    
    for alliance_name, groups in alliances_data.items():
        alliance = models.Alliance(name=alliance_name, organization_id=org.id)
        db.add(alliance)
        db.flush()
        
        for group_name in groups:
            group = models.Group(name=group_name, alliance_id=alliance.id)
            db.add(group)
            db.flush()
            
            # Добавляем сотрудников
            if group_name in employees_data:
                for emp_name in employees_data[group_name]:
                    employee = models.Employee(full_name=emp_name, group_id=group.id)
                    db.add(employee)
    
    # Создаем тестовых пользователей
    admin = models.User(
        username="admin",
        hashed_password=auth.get_password_hash("admin123"),
        role="admin"
    )
    db.add(admin)
    
    manager = models.User(
        username="manager",
        hashed_password=auth.get_password_hash("manager123"),
        role="manager"
    )
    db.add(manager)
    
    employee = models.User(
        username="employee",
        hashed_password=auth.get_password_hash("employee123"),
        role="employee"
    )
    db.add(employee)
    db.flush()
    
    # Привязываем сотрудника к пользователю
    first_employee = db.query(models.Employee).first()
    if first_employee:
        first_employee.user_id = employee.id
    
    db.commit()
    
    return {"status": "success", "message": "Тестовые данные созданы"}