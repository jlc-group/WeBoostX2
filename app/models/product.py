"""
Product and Product Group models
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, Text, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Product(BaseModel):
    """Individual product/SKU"""
    
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # SKU code e.g. "S1", "L7"
    name = Column(String(255), nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    can_allocate_budget = Column(Boolean, default=True)  # Allow budget allocation
    
    # Optional details
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    price = Column(Numeric(12, 2), nullable=True)
    image_url = Column(String(500), nullable=True)
    
    # External references
    tiktok_product_id = Column(String(100), nullable=True)
    shopee_product_id = Column(String(100), nullable=True)
    lazada_product_id = Column(String(100), nullable=True)


class ProductGroup(BaseModel):
    """Group of products for budget allocation"""
    
    __tablename__ = "product_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    
    # Products in this group (list of product codes)
    product_codes = Column(JSON, nullable=False, default=list)  # ["S1", "S2", "L7"]
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Budget allocation settings
    default_content_style_weights = Column(JSON, nullable=True)  # {"SALE": 60, "REVIEW": 30, "BRANDING": 10}
    
    # Relationships
    budget_allocations = relationship("BudgetAllocation", back_populates="product_group")
    abx_adgroups = relationship("ABXAdgroup", back_populates="product_group")

