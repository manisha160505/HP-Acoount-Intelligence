from fastapi import APIRouter, Depends, Query

from app.core.deps import require_admin_role
from app.database.mongodb import get_db
from app.schemas.usage import AnalyticsResponse
from app.services.analytics import build_analytics

router = APIRouter(prefix="/admin/analytics", tags=["Usage Analytics (Admin Only)"])


@router.get("", response_model=AnalyticsResponse)
def get_analytics(
    date_from: str | None = Query(None, alias="from",
                                  description="YYYY-MM-DD, inclusive, UTC"),
    date_to: str | None = Query(None, alias="to",
                                description="YYYY-MM-DD, inclusive, UTC"),
    current_user: dict = Depends(require_admin_role),
):
    return build_analytics(get_db(), date_from, date_to)
