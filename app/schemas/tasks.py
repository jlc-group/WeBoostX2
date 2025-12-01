"""
Schemas for task/job monitoring
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from app.models.task import TaskStatus


class TaskLogResponse(BaseModel):
    """Task log entry"""

    id: int
    task_name: str
    task_type: Optional[str] = None
    status: TaskStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    message: Optional[str] = None
    error_message: Optional[str] = None
    items_processed: int = 0
    items_success: int = 0
    items_failed: int = 0
    triggered_by: Optional[str] = None

    class Config:
        from_attributes = True


class SyncStatusResponse(BaseModel):
    """Sync status entry"""

    id: int
    entity_type: str
    platform: Optional[str] = None
    ad_account_id: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[TaskStatus] = None
    last_sync_message: Optional[str] = None
    total_items: int = 0
    last_items_synced: int = 0

    class Config:
        from_attributes = True


class ContentSyncConfig(BaseModel):
    """Config for content/organic refresh jobs"""

    organic_refresh_max_days: int = 7
    organic_refresh_interval_minutes: int = 60
    max_content_per_job: int = 100


class RunTaskRequest(BaseModel):
    """Request payload to trigger a task manually"""

    task_name: str

