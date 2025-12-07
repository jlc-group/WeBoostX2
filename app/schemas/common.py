"""
Common schemas used across the API
"""
from typing import Optional, Generic, TypeVar, List, Any
from pydantic import BaseModel
from datetime import datetime

T = TypeVar("T")


class ResponseBase(BaseModel):
    """Base response model"""
    success: bool = True
    message: Optional[str] = None


class DataResponse(ResponseBase, Generic[T]):
    """Response with data"""
    data: Optional[T] = None
    meta: Optional[Any] = None  # Additional metadata


class ListResponse(ResponseBase, Generic[T]):
    """Response with list data and pagination"""
    data: List[T] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    pages: int = 1


class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    detail: Optional[Any] = None


class PaginationParams(BaseModel):
    """Pagination parameters"""
    page: int = 1
    page_size: int = 20
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        return self.page_size


class DateRangeParams(BaseModel):
    """Date range filter parameters"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class SortParams(BaseModel):
    """Sort parameters"""
    sort_by: Optional[str] = None
    sort_order: str = "desc"  # asc or desc

