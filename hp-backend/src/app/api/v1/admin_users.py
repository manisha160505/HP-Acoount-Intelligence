from fastapi import APIRouter, Depends, Query, status

from app.core.deps import require_admin_role, require_super_admin
from app.database.mongodb import get_db
from app.schemas.admin_users import (
    AccountAssignment,
    AccountUser,
    AdminUserCreate,
    AdminUserCreated,
    AdminUserResponse,
    AdminUserStatusUpdate,
    AuditEntry,
    PasswordResetRequest,
    PasswordResetResponse,
    RoleUpdate,
)
from app.services import users_admin

router = APIRouter(prefix="/admin", tags=["User Management (Admin Only)"])


@router.post("/users", response_model=AdminUserCreated, status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, current_user: dict = Depends(require_admin_role)):
    return users_admin.create_user(get_db(), body, current_user)


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(current_user: dict = Depends(require_admin_role)):
    return users_admin.list_users(get_db())


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user_status(user_id: str, body: AdminUserStatusUpdate,
                       current_user: dict = Depends(require_admin_role)):
    return users_admin.set_active(get_db(), user_id, body.is_active, current_user)


@router.put("/users/{user_id}/role", response_model=AdminUserResponse)
def update_user_role(user_id: str, body: RoleUpdate,
                     current_user: dict = Depends(require_super_admin)):
    return users_admin.set_role(get_db(), user_id, body.role, current_user)


@router.put("/users/{user_id}/accounts", response_model=AdminUserResponse)
def update_user_accounts(user_id: str, body: AccountAssignment,
                         current_user: dict = Depends(require_admin_role)):
    return users_admin.set_accounts(get_db(), user_id, body.account_ids, current_user)


@router.post("/users/{user_id}/reset-password", response_model=PasswordResetResponse)
def reset_user_password(user_id: str, body: PasswordResetRequest,
                        current_user: dict = Depends(require_admin_role)):
    return users_admin.reset_password(get_db(), user_id, body.password, current_user)


@router.get("/accounts/{account_id}/users", response_model=list[AccountUser])
def account_users(account_id: str, current_user: dict = Depends(require_admin_role)):
    return users_admin.users_for_account(get_db(), account_id)


@router.get("/audit", response_model=list[AuditEntry])
def audit_log(user_id: str | None = None, limit: int = Query(200, ge=1, le=1000),
              current_user: dict = Depends(require_admin_role)):
    return users_admin.audit_log(get_db(), user_id, limit)
