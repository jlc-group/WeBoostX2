"""
Products and Product Groups API endpoints
"""
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db
from app.models import Product, ProductGroup, TargetingTemplate, AdAccount
from app.models.enums import (
    ObjectiveCode, 
    OBJECTIVE_CODE_TO_TIKTOK, 
    OBJECTIVE_CODE_TO_OPTIMIZATION,
    OBJECTIVE_CODE_TO_BILLING
)
from app.services.tiktok_ads_service import TikTokAdsService
from app.services.naming_service import NamingService


router = APIRouter(prefix="/products", tags=["products"])


# ============================================
# Pydantic Schemas
# ============================================

class ProductBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    is_active: bool = True
    can_allocate_budget: bool = True
    tiktok_product_id: Optional[str] = None
    shopee_product_id: Optional[str] = None
    lazada_product_id: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None
    can_allocate_budget: Optional[bool] = None
    tiktok_product_id: Optional[str] = None
    shopee_product_id: Optional[str] = None
    lazada_product_id: Optional[str] = None


class ProductResponse(ProductBase):
    id: int
    
    class Config:
        from_attributes = True


class ProductBulkStatusUpdate(BaseModel):
    """Payload สำหรับอัปเดตสถานะสินค้าแบบหลายตัวพร้อมกัน"""
    ids: List[int]
    is_active: bool


class ProductBulkAllocateUpdate(BaseModel):
    """Payload สำหรับอัปเดตสิทธิ์การจัดสรรงบของสินค้าแบบหลายตัวพร้อมกัน"""
    ids: List[int]
    can_allocate_budget: bool


class ProductBulkDelete(BaseModel):
    """Payload สำหรับลบสินค้าแบบหลายตัวพร้อมกัน (soft delete)"""
    ids: List[int]


class ProductGroupBase(BaseModel):
    name: str
    product_codes: List[str]
    is_active: bool = True
    default_content_style_weights: Optional[dict] = None


class ProductGroupCreate(ProductGroupBase):
    pass


class ProductGroupUpdate(BaseModel):
    name: Optional[str] = None
    product_codes: Optional[List[str]] = None
    is_active: Optional[bool] = None
    default_content_style_weights: Optional[dict] = None


class ProductGroupResponse(ProductGroupBase):
    id: int
    
    class Config:
        from_attributes = True


class ProductGroupBulkStatusUpdate(BaseModel):
    """Payload สำหรับอัปเดตสถานะ product group แบบหลายตัวพร้อมกัน"""
    ids: List[int]
    is_active: bool


class ProductGroupBulkDelete(BaseModel):
    """Payload สำหรับลบ product group แบบหลายตัวพร้อมกัน (soft delete)"""
    ids: List[int]


class AutoCreateAbxAdgroupsRequest(BaseModel):
    """
    Payload สำหรับ Auto Create ABX Adgroups สำหรับ Product Group
    
    ใช้สร้างชุด ABX Adgroups ตาม targeting x content_style ที่เลือก
    """
    advertiser_id: str
    campaign_id: str
    objective_code: str = "VV"  # VV, RCH, TRF, CVN
    targeting_ids: List[int]  # List of TargetingTemplate IDs
    content_styles: List[str]  # e.g. ["SALE", "ECOM", "REVIEW"]
    adgroups_per_style: int = 5  # จำนวน adgroup ต่อ targeting x style
    budget_per_adgroup: float = 500.0


class AutoCreateAbxAdgroupsResponse(BaseModel):
    """Response for Auto Create ABX Adgroups"""
    success: bool
    created_count: int
    failed_count: int
    adgroups: List[Dict]
    message: str


# ============================================
# Products CRUD
# ============================================

@router.get("", response_model=List[ProductResponse])
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all products with optional filtering (ไม่รวมรายการที่ถูกลบแบบ soft delete)"""
    query = db.query(Product).filter(Product.deleted_at.is_(None))
    
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Product.code.ilike(search_term)) | 
            (Product.name.ilike(search_term))
        )
    
    query = query.order_by(Product.code)
    return query.offset(skip).limit(limit).all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get single product by ID"""
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.deleted_at.is_(None)
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


@router.get("/code/{code}", response_model=ProductResponse)
def get_product_by_code(code: str, db: Session = Depends(get_db)):
    """Get single product by code"""
    product = db.query(Product).filter(
        Product.code == code,
        Product.deleted_at.is_(None)
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


@router.post("", response_model=ProductResponse)
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    """Create new product"""
    # Check if code already exists
    existing = db.query(Product).filter(Product.code == product_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product code '{product_in.code}' already exists")
    
    product = Product(**product_in.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int, 
    product_in: ProductUpdate, 
    db: Session = Depends(get_db)
):
    """Update product"""
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.deleted_at.is_(None)
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    
    db.commit()
    db.refresh(product)
    
    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Soft delete product"""
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.deleted_at.is_(None)
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Product deleted", "id": product_id}


@router.post("/bulk-status")
def bulk_update_product_status(
    payload: ProductBulkStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    อัปเดตสถานะ is_active ของสินค้าแบบหลายตัวพร้อมกัน
    ใช้ในหน้า Master Data > Products (bulk toggle Active/Inactive)
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No product IDs provided")

    updated = (
        db.query(Product)
        .filter(Product.id.in_(payload.ids))
        .update({Product.is_active: payload.is_active}, synchronize_session=False)
    )
    db.commit()

    return {"updated": updated, "is_active": payload.is_active}


@router.post("/bulk-allocate")
def bulk_update_product_allocate(
    payload: ProductBulkAllocateUpdate,
    db: Session = Depends(get_db),
):
    """
    อัปเดต can_allocate_budget ของสินค้าแบบหลายตัวพร้อมกัน
    ใช้ในหน้า Master Data > Products (bulk toggle จัดสรรงบได้/ไม่ได้)
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No product IDs provided")

    updated = (
        db.query(Product)
        .filter(Product.id.in_(payload.ids), Product.deleted_at.is_(None))
        .update({Product.can_allocate_budget: payload.can_allocate_budget}, synchronize_session=False)
    )
    db.commit()

    return {"updated": updated, "can_allocate_budget": payload.can_allocate_budget}


@router.post("/bulk-delete")
def bulk_delete_products(
    payload: ProductBulkDelete,
    db: Session = Depends(get_db),
):
    """
    ลบสินค้าแบบหลายตัวพร้อมกัน (soft delete)
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No product IDs provided")

    now = datetime.utcnow()

    updated = (
        db.query(Product)
        .filter(Product.id.in_(payload.ids), Product.deleted_at.is_(None))
        .update({Product.deleted_at: now}, synchronize_session=False)
    )
    db.commit()

    return {"deleted": updated}


# ============================================
# Product Groups CRUD
# ============================================

groups_router = APIRouter(prefix="/product-groups", tags=["product-groups"])


@groups_router.get("", response_model=List[ProductGroupResponse])
def get_product_groups(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all product groups with optional filtering (ไม่รวมรายการที่ถูกลบแบบ soft delete)"""
    query = db.query(ProductGroup).filter(ProductGroup.deleted_at.is_(None))
    
    if is_active is not None:
        query = query.filter(ProductGroup.is_active == is_active)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(ProductGroup.name.ilike(search_term))
    
    query = query.order_by(ProductGroup.name)
    return query.offset(skip).limit(limit).all()


@groups_router.get("/{group_id}", response_model=ProductGroupResponse)
def get_product_group(group_id: int, db: Session = Depends(get_db)):
    """Get single product group by ID"""
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    return group


@groups_router.post("", response_model=ProductGroupResponse)
def create_product_group(group_in: ProductGroupCreate, db: Session = Depends(get_db)):
    """Create new product group"""
    # Validate product codes exist
    if group_in.product_codes:
        existing_codes = [p.code for p in db.query(Product.code).filter(
            Product.code.in_(group_in.product_codes)
        ).all()]
        
        missing = set(group_in.product_codes) - set(existing_codes)
        if missing:
            raise HTTPException(
                status_code=400, 
                detail=f"Product codes not found: {', '.join(missing)}"
            )
    
    group = ProductGroup(**group_in.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    
    return group


@groups_router.put("/{group_id}", response_model=ProductGroupResponse)
def update_product_group(
    group_id: int, 
    group_in: ProductGroupUpdate, 
    db: Session = Depends(get_db)
):
    """Update product group"""
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    # Validate product codes if provided
    if group_in.product_codes is not None:
        existing_codes = [p.code for p in db.query(Product.code).filter(
            Product.code.in_(group_in.product_codes),
            Product.deleted_at.is_(None)
        ).all()]
        
        missing = set(group_in.product_codes) - set(existing_codes)
        if missing:
            raise HTTPException(
                status_code=400, 
                detail=f"Product codes not found: {', '.join(missing)}"
            )
    
    update_data = group_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(group, field, value)
    
    db.commit()
    db.refresh(group)
    
    return group


@groups_router.delete("/{group_id}")
def delete_product_group(group_id: int, db: Session = Depends(get_db)):
    """Soft delete product group"""
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    group.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Product group deleted", "id": group_id}


@groups_router.post("/bulk-status")
def bulk_update_product_group_status(
    payload: ProductGroupBulkStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    อัปเดต is_active ของ product group หลายรายการพร้อมกัน
    ใช้ในหน้า Master Data > Product Groups
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No product group IDs provided")

    updated = (
        db.query(ProductGroup)
        .filter(ProductGroup.id.in_(payload.ids), ProductGroup.deleted_at.is_(None))
        .update({ProductGroup.is_active: payload.is_active}, synchronize_session=False)
    )
    db.commit()

    return {"updated": updated, "is_active": payload.is_active}


@groups_router.post("/bulk-delete")
def bulk_delete_product_groups(
    payload: ProductGroupBulkDelete,
    db: Session = Depends(get_db),
):
    """
    ลบ product group หลายรายการพร้อมกัน (soft delete)
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No product group IDs provided")

    now = datetime.utcnow()
    updated = (
        db.query(ProductGroup)
        .filter(ProductGroup.id.in_(payload.ids), ProductGroup.deleted_at.is_(None))
        .update({ProductGroup.deleted_at: now}, synchronize_session=False)
    )
    db.commit()

    return {"deleted": updated}


@groups_router.get("/{group_id}/products", response_model=List[ProductResponse])
def get_products_in_group(group_id: int, db: Session = Depends(get_db)):
    """Get all products in a product group"""
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    if not group.product_codes:
        return []
    
    products = db.query(Product).filter(
        Product.code.in_(group.product_codes),
        Product.deleted_at.is_(None)
    ).order_by(Product.code).all()
    
    return products


@groups_router.post("/{group_id}/abx/preview")
def preview_abx_adgroups(
    group_id: int,
    request: AutoCreateAbxAdgroupsRequest,
    db: Session = Depends(get_db)
):
    """
    Preview ชื่อ ABX Adgroups ที่จะสร้าง (ไม่สร้างจริง)
    
    ใช้ดูรายการ adgroup names ก่อนกดสร้างจริง
    """
    # Get product group
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    if not group.product_codes:
        raise HTTPException(status_code=400, detail="Product group has no products")
    
    # Get targeting templates
    targeting_templates = db.query(TargetingTemplate).filter(
        TargetingTemplate.id.in_(request.targeting_ids)
    ).all()
    
    if not targeting_templates:
        raise HTTPException(status_code=400, detail="No valid targeting templates found")
    
    # Generate preview names
    preview_adgroups = []
    obj_code = request.objective_code.upper()
    
    for targeting in targeting_templates:
        for style in request.content_styles:
            for i in range(1, request.adgroups_per_style + 1):
                adgroup_name = NamingService.generate_adgroup_name(
                    product_codes=group.product_codes,
                    structure_code="ABX",
                    objective_code=obj_code,
                    targeting_code=targeting.name,
                    content_style_code=style,
                    index=i
                )
                preview_adgroups.append({
                    "name": adgroup_name,
                    "targeting": targeting.name,
                    "style": style,
                    "index": i,
                    "is_header": i == 1  # First one per targeting+style is header
                })
    
    return {
        "product_group": {
            "id": group.id,
            "name": group.name,
            "product_codes": group.product_codes
        },
        "objective_code": obj_code,
        "total_adgroups": len(preview_adgroups),
        "adgroups": preview_adgroups
    }


@groups_router.post("/{group_id}/abx/auto-create", response_model=AutoCreateAbxAdgroupsResponse)
def auto_create_abx_adgroups(
    group_id: int,
    request: AutoCreateAbxAdgroupsRequest,
    db: Session = Depends(get_db)
):
    """
    Auto Create ABX Adgroups สำหรับ Product Group
    
    สร้างชุด ABX Adgroups บน TikTok ตาม targeting x content_style ที่เลือก
    
    Flow:
    1. ตรวจสอบ Product Group
    2. ตรวจสอบ Advertiser Account
    3. ดึง Targeting Templates
    4. Generate ชื่อ Adgroups ตาม pattern: [Products]_ABX_<OBJ>_(<Targeting>)_<Style>#<Num>
    5. สร้าง Adgroups บน TikTok
    6. บันทึกลง Database (ABXAdgroup)
    """
    # Get product group
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    if not group.product_codes:
        raise HTTPException(status_code=400, detail="Product group has no products")
    
    # Validate advertiser
    ad_account = db.query(AdAccount).filter(
        AdAccount.external_account_id == request.advertiser_id,
        AdAccount.platform == "tiktok",
        AdAccount.is_active == True
    ).first()
    
    if not ad_account:
        raise HTTPException(status_code=400, detail="Invalid or inactive advertiser account")
    
    # Get targeting templates
    targeting_templates = db.query(TargetingTemplate).filter(
        TargetingTemplate.id.in_(request.targeting_ids)
    ).all()
    
    if not targeting_templates:
        raise HTTPException(status_code=400, detail="No valid targeting templates found")
    
    # Map objective code to TikTok optimization goal
    obj_code = request.objective_code.upper()
    try:
        objective_enum = ObjectiveCode(obj_code)
        optimization_goal = OBJECTIVE_CODE_TO_OPTIMIZATION.get(objective_enum, "VIDEO_VIEW")
    except ValueError:
        optimization_goal = "VIDEO_VIEW"
    
    # Create adgroups
    created_adgroups = []
    failed_adgroups = []
    
    for targeting in targeting_templates:
        # Get targeting settings from template
        targeting_settings = None
        if targeting.settings:
            targeting_settings = targeting.settings
        
        for style in request.content_styles:
            for i in range(1, request.adgroups_per_style + 1):
                adgroup_name = NamingService.generate_adgroup_name(
                    product_codes=group.product_codes,
                    structure_code="ABX",
                    objective_code=obj_code,
                    targeting_code=targeting.name,
                    content_style_code=style,
                    index=i
                )
                
                # Create adgroup on TikTok
                result = TikTokAdsService.create_adgroup(
                    advertiser_id=request.advertiser_id,
                    campaign_id=request.campaign_id,
                    adgroup_name=adgroup_name,
                    targeting=targeting_settings,
                    budget=request.budget_per_adgroup,
                    optimization_goal=optimization_goal
                )
                
                if result.get("success"):
                    created_adgroups.append({
                        "name": adgroup_name,
                        "adgroup_id": result.get("adgroup_id"),
                        "targeting": targeting.name,
                        "style": style,
                        "index": i
                    })
                else:
                    failed_adgroups.append({
                        "name": adgroup_name,
                        "error": result.get("message", "Unknown error"),
                        "targeting": targeting.name,
                        "style": style,
                        "index": i
                    })
    
    # Generate response
    total_created = len(created_adgroups)
    total_failed = len(failed_adgroups)
    
    if total_created == 0 and total_failed > 0:
        return AutoCreateAbxAdgroupsResponse(
            success=False,
            created_count=0,
            failed_count=total_failed,
            adgroups=failed_adgroups,
            message=f"Failed to create all {total_failed} adgroups"
        )
    
    return AutoCreateAbxAdgroupsResponse(
        success=True,
        created_count=total_created,
        failed_count=total_failed,
        adgroups=created_adgroups,
        message=f"Created {total_created} adgroups" + (f", {total_failed} failed" if total_failed > 0 else "")
    )

