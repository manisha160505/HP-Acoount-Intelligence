from fastapi import APIRouter, Depends, Query

from app.core.deps import require_user_role
from app.database.mongodb import get_db
from app.schemas.usage import MyActivityResponse
from app.services.analytics import build_my_activity

router = APIRouter(prefix="/me", tags=["Usage Analytics (Own Activity)"])


@router.get("/activity", response_model=MyActivityResponse)
def get_my_activity(
    date_from: str | None = Query(None, alias="from",
                                  description="YYYY-MM-DD, inclusive, UTC"),
    date_to: str | None = Query(None, alias="to",
                                description="YYYY-MM-DD, inclusive, UTC"),
    current_user: dict = Depends(require_user_role),
):
    """The caller's own usage. There is no user parameter: whose activity this
    is comes only from the token."""
    return build_my_activity(get_db(), current_user, date_from, date_to)
