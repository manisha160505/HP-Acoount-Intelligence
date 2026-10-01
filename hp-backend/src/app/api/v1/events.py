from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.core.deps import get_current_user_flexible
from app.database.mongodb import get_db
from app.errors import APIError, ErrorCode
from app.schemas.usage import UsageEventBatch, UsageEventBatchResult
from app.services.usage import record_client_events

router = APIRouter(prefix="/events", tags=["Usage Events"])


@router.post("", response_model=UsageEventBatchResult)
async def submit_events(request: Request,
                        current_user: dict = Depends(get_current_user_flexible)):
    """Record a batch of feature views and heartbeats for the signed-in user.

    Authenticated by the Bearer header, or `?token=` - the page-close flush
    goes out through `navigator.sendBeacon`, which cannot set headers and
    sends its body as text/plain. That is why the body is parsed here rather
    than declared as a JSON body parameter FastAPI would reject by content
    type. `user_id` always comes from the token; one in the body is ignored.
    """
    raw = await request.body()
    try:
        batch = UsageEventBatch.model_validate_json(raw or b"{}")
    except ValidationError as exc:
        raise APIError(ErrorCode.VALIDATION_ERROR,
                       log_context={"errors": exc.errors(include_url=False)[:5]}) from exc
    return UsageEventBatchResult(accepted=record_client_events(get_db(), current_user,
                                                               batch.events))
