from pydantic import BaseModel
from datetime import date, time, datetime
from typing import Optional, List

class ShiftCreate(BaseModel):
    date: date
    start_time: str
    end_time: Optional[str] = None

class ShiftResponse(BaseModel):
    id: int
    date: date
    start_time: str
    end_time: Optional[str]
    status: str
    
    class Config:
        from_attributes = True

class EmployeeCreate(BaseModel):
    full_name: str
    alliance_name: str
    group_name: str

class EmployeeResponse(BaseModel):
    id: int
    full_name: str
    alliance_name: str
    group_name: str
    shifts: List[ShiftResponse] = []
    
    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "employee"
    employee_id: Optional[int] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class ScheduleRangeCreate(BaseModel):
    employee_id: int
    shifts: List[ShiftCreate]