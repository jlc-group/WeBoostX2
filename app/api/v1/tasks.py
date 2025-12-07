"""
Task / Job monitoring API endpoints
"""
from typing import Optional, Dict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.models.task import TaskLog, SyncStatus, TaskStatus
from app.models.system import AppSetting
from app.schemas.tasks import (
    TaskLogResponse,
    SyncStatusResponse,
    ContentSyncConfig,
    RunTaskRequest,
)
from app.schemas.common import ListResponse, DataResponse
from app.models.user import User


router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("/logs", response_model=ListResponse[TaskLogResponse])
def list_task_logs(
    limit: int = Query(50, ge=1, le=200),
    task_name: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get recent task logs (admin only)."""

    query = db.query(TaskLog).order_by(TaskLog.started_at.desc().nullslast())

    if task_name:
        query = query.filter(TaskLog.task_name == task_name)
    if status:
        query = query.filter(TaskLog.status == status)

    logs = query.limit(limit).all()

    return ListResponse(
        data=[TaskLogResponse.model_validate(log) for log in logs],
        total=len(logs),
        page=1,
        page_size=limit,
        pages=1,
    )


@router.get("/sync-status", response_model=ListResponse[SyncStatusResponse])
def list_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get sync status for entities (admin only)."""

    rows = db.query(SyncStatus).order_by(SyncStatus.entity_type, SyncStatus.platform).all()

    return ListResponse(
        data=[SyncStatusResponse.model_validate(row) for row in rows],
        total=len(rows),
        page=1,
        page_size=len(rows) or 1,
        pages=1,
    )


def _get_content_sync_settings_map(db: Session) -> Dict[str, AppSetting]:
    """Helper: get content-sync related settings as mapping key -> AppSetting."""
    rows = (
        db.query(AppSetting)
        .filter(AppSetting.category == "content_sync")
        .all()
    )
    return {row.key: row for row in rows}


def _cleanup_stale_running_tasks(db: Session, stale_minutes: int = 15) -> None:
    """
    Mark RUNNING tasks ที่นานเกินกำหนดให้เป็น FAILED (กันค่าค้างจาก server restart).
    """
    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    stale_tasks = (
        db.query(TaskLog)
        .filter(
            TaskLog.status == TaskStatus.RUNNING,
            TaskLog.started_at != None,  # noqa: E711
            TaskLog.started_at < cutoff,
        )
        .all()
    )
    if not stale_tasks:
        return

    for t in stale_tasks:
        t.status = TaskStatus.FAILED
        if not t.error_message:
            t.error_message = "Auto-marked as FAILED: stale RUNNING task (server restart/timeout)"
        # ไม่ต้องคำนวณ duration เพื่อเลี่ยง timezone ปนกัน แค่ปิดงานให้เรียบร้อยพอ
        if not t.completed_at:
            t.completed_at = datetime.utcnow()
    db.commit()


@router.get("/config/content-sync", response_model=DataResponse[ContentSyncConfig])
def get_content_sync_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get content/organic refresh job config (admin only)."""

    settings_map = _get_content_sync_settings_map(db)

    def iv(key: str, default: int) -> int:
        row = settings_map.get(key)
        if not row or row.value is None:
            return default
        try:
            return int(row.value)
        except ValueError:
            return default

    cfg = ContentSyncConfig(
        organic_refresh_max_days=iv("organic_refresh_max_days", 7),
        organic_refresh_interval_minutes=iv("organic_refresh_interval_minutes", 60),
        max_content_per_job=iv("max_content_per_job", 100),
    )

    return DataResponse(data=cfg)


@router.put("/config/content-sync", response_model=DataResponse[ContentSyncConfig])
def update_content_sync_config(
    payload: ContentSyncConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update content/organic refresh job config (admin only)."""

    settings_map = _get_content_sync_settings_map(db)

    def upsert_int(key: str, value: int):
        row = settings_map.get(key)
        if row is None:
            row = AppSetting(
                key=key,
                value=str(value),
                category="content_sync",
                is_secret=False,
            )
            db.add(row)
        else:
            row.value = str(value)
            row.is_secret = False

    upsert_int("organic_refresh_max_days", payload.organic_refresh_max_days)
    upsert_int("organic_refresh_interval_minutes", payload.organic_refresh_interval_minutes)
    upsert_int("max_content_per_job", payload.max_content_per_job)

    db.commit()

    return DataResponse(data=payload, message="Content sync config updated")


@router.post("/run", response_model=DataResponse[dict])
def run_task_now(
    request: RunTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Run a specific background task immediately (admin only).

    Supported task_name values:
    - sync_all_content
    - sync_all_ads
    - sync_tiktok_content
    - refresh_tiktok_organic
    - sync_campaigns_adgroups
    """

    from app.tasks import sync_tasks

    task_name = request.task_name

    result: Dict = {}

    if task_name == "sync_all_content":
        sync_tasks.sync_all_content()
        result = {"task": "sync_all_content", "status": "queued"}
    elif task_name == "sync_all_ads":
        sync_tasks.sync_all_ads()
        result = {"task": "sync_all_ads", "status": "queued"}
    elif task_name == "sync_tiktok_content":
        r = sync_tasks.sync_tiktok_content()
        result = {"task": "sync_tiktok_content", **r}
    elif task_name == "refresh_tiktok_organic":
        r = sync_tasks.refresh_tiktok_organic()
        result = {"task": "refresh_tiktok_organic", **r}
    elif task_name == "sync_campaigns_adgroups":
        r = sync_tasks.sync_campaigns_adgroups()
        result = {"task": "sync_campaigns_adgroups", **r}
    else:
        return DataResponse(
            success=False,
            message=f"Unsupported task_name: {task_name}",
        )

    return DataResponse(
        data=result,
        message=f"Task '{task_name}' executed",
    )


