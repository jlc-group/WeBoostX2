"""
Authentication API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.core.deps import get_db, get_current_user, require_admin
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.models.user import User
from app.models.enums import UserStatus, UserRole
from app.schemas.auth import (
    Token,
    LoginRequest,
    RegisterRequest,
    UserResponse,
    UserUpdate,
    PasswordChange,
    RefreshTokenRequest,
)
from app.schemas.common import DataResponse, ListResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=DataResponse[Token])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login and get access token"""
    
    # Find user by email
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check user status
    if user.status == UserStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval"
        )
    
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active"
        )
    
    # Create tokens
    access_token = create_access_token(
        subject=user.id,
        additional_claims={"role": user.role.value}
    )
    refresh_token = create_refresh_token(subject=user.id)
    
    return DataResponse(
        data=Token(
            access_token=access_token,
            refresh_token=refresh_token
        ),
        message="Login successful"
    )


@router.post("/register", response_model=DataResponse[UserResponse])
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register new user (requires admin approval)"""
    
    # Check if email already exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user
    user = User(
        email=request.email,
        password_hash=get_password_hash(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        display_name=request.display_name,
        role=UserRole.VIEWER,  # Default role
        status=UserStatus.PENDING,  # Requires approval
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return DataResponse(
        data=UserResponse.model_validate(user),
        message="Registration successful. Please wait for admin approval."
    )


@router.post("/refresh", response_model=DataResponse[Token])
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token"""
    
    user_id = verify_token(request.refresh_token, token_type="refresh")
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    access_token = create_access_token(
        subject=user.id,
        additional_claims={"role": user.role.value}
    )
    new_refresh_token = create_refresh_token(subject=user.id)
    
    return DataResponse(
        data=Token(
            access_token=access_token,
            refresh_token=new_refresh_token
        )
    )


@router.get("/me", response_model=DataResponse[UserResponse])
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return DataResponse(data=UserResponse.model_validate(current_user))


@router.put("/me", response_model=DataResponse[UserResponse])
def update_current_user(
    request: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user profile"""
    
    if request.first_name is not None:
        current_user.first_name = request.first_name
    if request.last_name is not None:
        current_user.last_name = request.last_name
    if request.display_name is not None:
        current_user.display_name = request.display_name
    if request.phone is not None:
        current_user.phone = request.phone
    
    db.commit()
    db.refresh(current_user)
    
    return DataResponse(
        data=UserResponse.model_validate(current_user),
        message="Profile updated"
    )


@router.post("/change-password", response_model=DataResponse)
def change_password(
    request: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password"""
    
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    current_user.password_hash = get_password_hash(request.new_password)
    db.commit()
    
    return DataResponse(message="Password changed successfully")


# ============================================
# Admin endpoints
# ============================================


@router.get("/users", response_model=ListResponse[UserResponse])
def list_users(
    status: Optional[UserStatus] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List users (admin only, optional status filter)"""

    query = db.query(User)
    if status is not None:
        query = query.filter(User.status == status)

    users = query.order_by(User.id.desc()).all()
    total = len(users)

    return ListResponse(
        data=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=1,
        page_size=max(total, 1),
        pages=1,
    )


@router.get("/users/pending", response_model=ListResponse[UserResponse])
def get_pending_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get pending users (admin only)"""

    users = db.query(User).filter(User.status == UserStatus.PENDING).all()

    return ListResponse(
        data=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@router.post("/users/{user_id}/approve", response_model=DataResponse[UserResponse])
def approve_user(
    user_id: int,
    role: UserRole = UserRole.VIEWER,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve pending user (admin only)"""

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.status = UserStatus.ACTIVE
    user.role = role
    user.approved_by = current_user.id

    db.commit()
    db.refresh(user)

    return DataResponse(
        data=UserResponse.model_validate(user),
        message=f"User approved with role: {role.value}",
    )


@router.post("/users/{user_id}/role", response_model=DataResponse[UserResponse])
def update_user_role(
    user_id: int,
    role: UserRole,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update user role (admin only)"""
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.role = role
    db.commit()
    db.refresh(user)
    
    return DataResponse(
        data=UserResponse.model_validate(user),
        message=f"User role updated to: {role.value}"
    )

