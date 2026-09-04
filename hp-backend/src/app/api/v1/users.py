from fastapi import APIRouter, Depends
from app.core.deps import require_user_role, require_admin_role

router = APIRouter(prefix="/protected", tags=["Protected Verification Endpoints"])

@router.get("/user-area")
def user_area(current_user: dict = Depends(require_user_role)):
    return {
        "status": "success",
        "message": f"Welcome User/Admin: {current_user['full_name']}",
        "user": current_user
    }

@router.get("/admin-area")
def admin_area(current_user: dict = Depends(require_admin_role)):
    return {
        "status": "success",
        "message": f"Welcome Administrator: {current_user['full_name']}",
        "user": current_user
    }
