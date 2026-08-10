from fastapi import APIRouter, Depends, HTTPException
from ..schemas.employee import EmployeeCreate, EmployeeUpdate, EmployeeResponse
from ..config import db
from .auth import get_current_user
from ..models.employee import employee_helper
from datetime import datetime
from bson import ObjectId

router = APIRouter(prefix="/employees", tags=["Employees"])

@router.get("", response_model=list[EmployeeResponse])
async def get_employees(active_only: bool = True, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    query = {"tenant_id": tenant, "is_active": True} if active_only else {"tenant_id": tenant}
    cursor = db.employees.find(query)
    employees = []
    async for emp in cursor:
        employees.append(employee_helper(emp))
    return employees

@router.post("", response_model=EmployeeResponse)
async def create_employee(emp: EmployeeCreate, current_user=Depends(get_current_user)):
    emp_dict = emp.dict()
    emp_dict["tenant_id"] = current_user.get("tenant_id")
    emp_dict["created_at"] = datetime.utcnow()
    result = await db.employees.insert_one(emp_dict)
    new_emp = await db.employees.find_one({"_id": result.inserted_id})
    return employee_helper(new_emp)

@router.put("/{emp_id}", response_model=EmployeeResponse)
async def update_employee(emp_id: str, update: EmployeeUpdate, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(emp_id)
    except:
        raise HTTPException(404, "Invalid employee ID")
    update_dict = {k: v for k, v in update.dict().items() if v is not None}
    result = await db.employees.update_one({"_id": obj_id, "tenant_id": tenant}, {"$set": update_dict})
    if result.matched_count == 0:
        raise HTTPException(404, "Employee not found")
    updated = await db.employees.find_one({"_id": obj_id})
    return employee_helper(updated)

@router.delete("/{emp_id}")
async def deactivate_employee(emp_id: str, current_user=Depends(get_current_user)):
    tenant = current_user.get("tenant_id")
    try:
        obj_id = ObjectId(emp_id)
    except:
        raise HTTPException(404, "Invalid employee ID")
    result = await db.employees.update_one({"_id": obj_id, "tenant_id": tenant}, {"$set": {"is_active": False}})
    if result.matched_count == 0:
        raise HTTPException(404, "Employee not found")
    return {"status": "deactivated"}
    