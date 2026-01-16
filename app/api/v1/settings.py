"""
Settings API endpoints (Ad accounts, platform configs)
"""
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_admin
from app.models.enums import Platform
from app.models.platform import AdAccount
from app.models.system import AppSetting
from app.models.user import User
from app.schemas.common import DataResponse, ListResponse
from app.schemas.settings import (
    AdAccountCreate,
    AdAccountResponse,
    AdAccountUpdate,
    TikTokChannelsConfig,
    TikTokConfig,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/ad-accounts", response_model=ListResponse[AdAccountResponse])
def list_ad_accounts(
    platform: Optional[Platform] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List ad accounts (optionally filter by platform)"""

    query = db.query(AdAccount)
    if platform is not None:
        query = query.filter(AdAccount.platform == platform)

    accounts = query.order_by(AdAccount.id.desc()).all()

    return ListResponse(
        data=[
            AdAccountResponse(
                id=a.id,
                name=a.name,
                platform=a.platform,
                external_account_id=a.external_account_id,
                is_active=a.is_active if a.is_active is not None else True,
                timezone=a.timezone,
                currency=a.currency,
            )
            for a in accounts
        ],
        total=len(accounts),
    )


@router.post("/ad-accounts", response_model=DataResponse[AdAccountResponse])
def create_ad_account(
    payload: AdAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create new ad account"""

    # Simple duplicate check for same platform + external id
    existing = (
        db.query(AdAccount)
        .filter(
            AdAccount.platform == payload.platform,
            AdAccount.external_account_id == payload.external_account_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ad account already exists for this platform and ID",
        )

    account = AdAccount(
        name=payload.name,
        platform=payload.platform,
        external_account_id=payload.external_account_id,
        is_active=payload.is_active if hasattr(payload, 'is_active') else True,
        timezone=payload.timezone,
        currency=payload.currency or "THB",
        config=payload.config,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return DataResponse(
        data=AdAccountResponse(
            id=account.id,
            name=account.name,
            platform=account.platform,
            external_account_id=account.external_account_id,
            is_active=account.is_active if account.is_active is not None else True,
            timezone=account.timezone,
            currency=account.currency,
        ),
        message="Ad account created",
    )


@router.put("/ad-accounts/{account_id}", response_model=DataResponse[AdAccountResponse])
async def update_ad_account(
    account_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update ad account"""

    # Parse body manually to avoid 422 when client sends non-object payload
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload must be an object",
        )

    payload = AdAccountUpdate(**body)

    # Debug log payload for troubleshooting
    print(f"[update_ad_account] payload received: {payload.model_dump()}")

    account = db.query(AdAccount).filter(AdAccount.id == account_id).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ad account not found",
        )

    if payload.name is not None:
        account.name = payload.name
    if payload.is_active is not None:
        account.is_active = payload.is_active
    if payload.timezone is not None:
        account.timezone = payload.timezone
    if payload.currency is not None:
        account.currency = payload.currency
    if payload.config is not None:
        account.config = payload.config

    db.commit()
    db.refresh(account)

    return DataResponse(
        data=AdAccountResponse(
            id=account.id,
            name=account.name,
            platform=account.platform,
            external_account_id=account.external_account_id,
            is_active=account.is_active if account.is_active is not None else True,
            timezone=account.timezone,
            currency=account.currency,
        ),
        message="Ad account updated",
    )


def _get_tiktok_settings_map(db: Session) -> Dict[str, AppSetting]:
    """Helper: get TikTok-related settings as mapping key -> AppSetting."""
    rows = (
        db.query(AppSetting)
        .filter(AppSetting.category == "tiktok")
        .all()
    )
    return {row.key: row for row in rows}


@router.get("/tiktok-config", response_model=DataResponse[TikTokConfig])
def get_tiktok_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get TikTok API configuration (admin only)."""

    settings_map = _get_tiktok_settings_map(db)

    def v(key: str) -> Optional[str]:
        row = settings_map.get(key)
        return row.value if row else None

    cfg = TikTokConfig(
        business_id=v("tiktok_business_id"),
        client_id=v("tiktok_client_id"),
        client_secret=v("tiktok_client_secret"),
        refresh_token=v("tiktok_refresh_token"),
        direct_access_token=v("tiktok_access_token"),
    )

    return DataResponse(data=cfg)


@router.put("/tiktok-config", response_model=DataResponse[TikTokConfig])
def update_tiktok_config(
    payload: TikTokConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update TikTok API configuration (admin only)."""

    settings_map = _get_tiktok_settings_map(db)

    def upsert(key: str, value: Optional[str], is_secret: bool):
        if value is None:
            return
        row = settings_map.get(key)
        if row is None:
            row = AppSetting(
                key=key,
                value=value,
                category="tiktok",
                is_secret=is_secret,
            )
            db.add(row)
        else:
            row.value = value
            row.is_secret = is_secret

    upsert("tiktok_business_id", payload.business_id, False)
    upsert("tiktok_client_id", payload.client_id, True)
    upsert("tiktok_client_secret", payload.client_secret, True)
    upsert("tiktok_refresh_token", payload.refresh_token, True)
    upsert("tiktok_access_token", payload.direct_access_token, True)

    db.commit()

    # Return latest values
    new_map = _get_tiktok_settings_map(db)

    def v(key: str) -> Optional[str]:
        row = new_map.get(key)
        return row.value if row else None

    cfg = TikTokConfig(
        business_id=v("tiktok_business_id"),
        client_id=v("tiktok_client_id"),
        client_secret=v("tiktok_client_secret"),
        refresh_token=v("tiktok_refresh_token"),
        direct_access_token=v("tiktok_access_token"),
    )

    return DataResponse(
        data=cfg,
        message="TikTok settings updated",
    )


@router.get(
    "/tiktok-channels",
    response_model=DataResponse[TikTokChannelsConfig],
)
def get_tiktok_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get list of official TikTok channels (admin only)."""

    settings_map = _get_tiktok_settings_map(db)
    row = settings_map.get("tiktok_official_channels")

    channels: List[str] = []
    if row and row.value:
        try:
            loaded = json.loads(row.value)
            if isinstance(loaded, list):
                channels = [str(x) for x in loaded if str(x).strip()]
        except Exception:
            # ถ้า parse ไม่ได้ ให้ปล่อยเป็น list ว่าง
            pass

    return DataResponse(data=TikTokChannelsConfig(channels=channels))


@router.put(
    "/tiktok-channels",
    response_model=DataResponse[TikTokChannelsConfig],
)
def update_tiktok_channels(
    payload: TikTokChannelsConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update official TikTok channels (admin only)."""

    settings_map = _get_tiktok_settings_map(db)
    channels = [c.strip() for c in payload.channels if c.strip()]
    value = json.dumps(channels, ensure_ascii=False)

    row = settings_map.get("tiktok_official_channels")
    if row is None:
        row = AppSetting(
            key="tiktok_official_channels",
            value=value,
            category="tiktok",
            is_secret=False,
        )
        db.add(row)
    else:
        row.value = value
        row.is_secret = False

    db.commit()

    return DataResponse(
        data=TikTokChannelsConfig(channels=channels),
        message="TikTok official channels updated",
    )

