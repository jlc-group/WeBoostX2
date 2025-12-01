"""
Task and job logging models
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Enum
import enum

from app.models.base import BaseModel


class TaskStatus(str, enum.Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskLog(BaseModel):
    """Log of background task executions"""
    
    __tablename__ = "task_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Task identification
    task_name = Column(String(100), nullable=False, index=True)
    task_type = Column(String(50), nullable=True)  # sync, optimization, report, etc.
    
    # Execution
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Duration (seconds)
    duration_seconds = Column(Integer, nullable=True)
    
    # Results
    message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)
    
    # Statistics
    items_processed = Column(Integer, default=0)
    items_success = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    
    # Additional data
    input_params = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    
    # Trigger info
    triggered_by = Column(String(100), nullable=True)  # scheduler, user, api


class SyncStatus(BaseModel):
    """Track sync status for each entity type"""
    
    __tablename__ = "sync_status"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # What is being synced
    entity_type = Column(String(50), nullable=False, index=True)  # content, campaign, ad, etc.
    platform = Column(String(50), nullable=True, index=True)
    ad_account_id = Column(Integer, nullable=True, index=True)
    
    # Last sync info
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(Enum(TaskStatus), nullable=True)
    last_sync_message = Column(Text, nullable=True)
    
    # Sync stats
    total_items = Column(Integer, default=0)
    last_items_synced = Column(Integer, default=0)
    
    # Next scheduled sync
    next_sync_at = Column(DateTime(timezone=True), nullable=True)

