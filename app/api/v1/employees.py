"""
Employee API endpoints
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.employee import Employee, Influencer
from app.schemas.common import DataResponse, ListResponse

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get("", response_model=ListResponse)
def get_employees(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all employees with pagination"""
    
    query = db.query(Employee).filter(Employee.deleted_at.is_(None))
    
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    
    if search:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Employee.employee_code.ilike(f"%{search}%"),
                Employee.first_name.ilike(f"%{search}%"),
                Employee.last_name.ilike(f"%{search}%"),
                Employee.nickname.ilike(f"%{search}%")
            )
        )
    
    total = query.count()
    
    employees = query.order_by(Employee.first_name)\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    data = []
    for emp in employees:
        data.append({
            "id": emp.id,
            "employee_code": emp.employee_code,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "nickname": emp.nickname,
            "full_name": emp.full_name,
            "display_name": emp.display_name,
            "department": emp.department,
            "position": emp.position,
            "email": emp.email,
            "phone": emp.phone,
            "is_active": emp.is_active,
            "tiktok_username": emp.tiktok_username
        })
    
    return ListResponse(
        success=True,
        data=data,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.post("")
def create_employee(payload: dict, db: Session = Depends(get_db)):
    """Create a new employee"""
    
    # Check if employee_code already exists
    existing = db.query(Employee).filter(
        Employee.employee_code == payload.get("employee_code"),
        Employee.deleted_at.is_(None)
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Employee code already exists")
    
    employee = Employee(
        employee_code=payload.get("employee_code"),
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        nickname=payload.get("nickname"),
        department=payload.get("department"),
        position=payload.get("position"),
        email=payload.get("email"),
        phone=payload.get("phone"),
        tiktok_username=payload.get("tiktok_username"),
        is_active=payload.get("is_active", True)
    )
    
    db.add(employee)
    db.commit()
    db.refresh(employee)
    
    return DataResponse(
        success=True,
        data={"id": employee.id},
        message="Employee created"
    )


@router.get("/{employee_id}")
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    """Get single employee"""
    
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.deleted_at.is_(None)
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    return DataResponse(
        success=True,
        data={
            "id": employee.id,
            "employee_code": employee.employee_code,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "nickname": employee.nickname,
            "full_name": employee.full_name,
            "department": employee.department,
            "position": employee.position,
            "email": employee.email,
            "phone": employee.phone,
            "is_active": employee.is_active,
            "tiktok_username": employee.tiktok_username,
            "notes": employee.notes
        }
    )


@router.put("/{employee_id}")
def update_employee(employee_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update employee"""
    
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.deleted_at.is_(None)
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    for field in ["first_name", "last_name", "nickname", "department", "position", 
                  "email", "phone", "tiktok_username", "notes"]:
        if field in payload:
            setattr(employee, field, payload[field])
    
    if "is_active" in payload:
        employee.is_active = payload["is_active"]
    
    db.commit()
    
    return DataResponse(
        success=True,
        message="Employee updated"
    )


@router.delete("/{employee_id}")
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    """Soft delete employee"""
    from datetime import datetime
    
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.deleted_at.is_(None)
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    employee.deleted_at = datetime.utcnow()
    db.commit()
    
    return DataResponse(
        success=True,
        message="Employee deleted"
    )


# Influencer endpoints
influencer_router = APIRouter(prefix="/influencers", tags=["Influencers"])


@influencer_router.get("", response_model=ListResponse)
def get_influencers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    is_active: Optional[bool] = None,
    tier: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all influencers with pagination"""
    
    query = db.query(Influencer).filter(Influencer.deleted_at.is_(None))
    
    if is_active is not None:
        query = query.filter(Influencer.is_active == is_active)
    
    if tier:
        query = query.filter(Influencer.tier == tier)
    
    if search:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Influencer.name.ilike(f"%{search}%"),
                Influencer.tiktok_username.ilike(f"%{search}%"),
                Influencer.instagram_username.ilike(f"%{search}%")
            )
        )
    
    total = query.count()
    
    influencers = query.order_by(Influencer.name)\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    data = []
    for inf in influencers:
        data.append({
            "id": inf.id,
            "name": inf.name,
            "display_name": inf.display_name,
            "tiktok_username": inf.tiktok_username,
            "instagram_username": inf.instagram_username,
            "tier": inf.tier,
            "default_rate": float(inf.default_rate) if inf.default_rate else None,
            "currency": inf.currency,
            "total_contents": inf.total_contents,
            "total_cost_paid": float(inf.total_cost_paid) if inf.total_cost_paid else 0,
            "tiktok_followers": inf.tiktok_followers,
            "is_active": inf.is_active
        })
    
    return ListResponse(
        success=True,
        data=data,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@influencer_router.post("")
def create_influencer(payload: dict, db: Session = Depends(get_db)):
    """Create a new influencer"""
    
    influencer = Influencer(
        name=payload.get("name"),
        tiktok_username=payload.get("tiktok_username"),
        tiktok_user_id=payload.get("tiktok_user_id"),
        facebook_page=payload.get("facebook_page"),
        instagram_username=payload.get("instagram_username"),
        tier=payload.get("tier"),
        default_rate=payload.get("default_rate"),
        currency=payload.get("currency", "THB"),
        contact_info=payload.get("contact_info"),
        is_active=payload.get("is_active", True),
        notes=payload.get("notes")
    )
    
    db.add(influencer)
    db.commit()
    db.refresh(influencer)
    
    return DataResponse(
        success=True,
        data={"id": influencer.id},
        message="Influencer created"
    )


@influencer_router.put("/{influencer_id}")
def update_influencer(influencer_id: int, payload: dict, db: Session = Depends(get_db)):
    """Update influencer"""
    
    influencer = db.query(Influencer).filter(
        Influencer.id == influencer_id,
        Influencer.deleted_at.is_(None)
    ).first()
    
    if not influencer:
        raise HTTPException(status_code=404, detail="Influencer not found")
    
    for field in ["name", "tiktok_username", "instagram_username", "tier", 
                  "default_rate", "facebook_page", "contact_info", "notes"]:
        if field in payload:
            setattr(influencer, field, payload[field])
    
    if "is_active" in payload:
        influencer.is_active = payload["is_active"]
    
    db.commit()
    
    return DataResponse(
        success=True,
        message="Influencer updated"
    )

