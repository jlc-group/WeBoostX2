"""
Products and Product Groups API endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db
from app.models import Product, ProductGroup


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
    """Get all products with optional filtering"""
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
    from datetime import datetime
    
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.deleted_at.is_(None)
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Product deleted", "id": product_id}


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
    """Get all product groups with optional filtering"""
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
            Product.code.in_(group_in.product_codes),
            Product.deleted_at.is_(None)
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
    from datetime import datetime
    
    group = db.query(ProductGroup).filter(
        ProductGroup.id == group_id,
        ProductGroup.deleted_at.is_(None)
    ).first()
    
    if not group:
        raise HTTPException(status_code=404, detail="Product group not found")
    
    group.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Product group deleted", "id": group_id}


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

