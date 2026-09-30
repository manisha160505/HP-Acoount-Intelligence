from fastapi import APIRouter, Depends, status

from app.core.deps import require_admin_role
from app.database.mongodb import get_db
from app.schemas.admin_users import AdminUserCreate, AdminUserResponse, AdminUserStatusUpdate
from app.services import users_admin

router = APIRouter(prefix="/admin/users", tags=["User Management (Admin Only)"])


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, current_user: dict = Depends(require_admin_role)):
    return users_admin.create_user(get_db(), body)


@router.get("", response_model=list[AdminUserResponse])
def list_users(current_user: dict = Depends(require_admin_role)):
    return users_admin.list_users(get_db())


@router.patch("/{user_id}", response_model=AdminUserResponse)
def update_user_status(user_id: str, body: AdminUserStatusUpdate,
                       current_user: dict = Depends(require_admin_role)):
    return users_admin.set_active(get_db(), user_id, body.is_active, current_user["id"])
