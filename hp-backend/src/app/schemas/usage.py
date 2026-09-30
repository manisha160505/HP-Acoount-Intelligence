from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The largest batch one POST may carry. The browser flushes every 10 seconds,
# so a real client sends a handful; this only bounds a misbehaving one.
MAX_EVENTS_PER_BATCH = 100


class UsageEventIn(BaseModel):
    """One event as the browser reports it.

    Identity is not part of this model: `user_id` and `ts` are set by the
    server from the token and the clock. `extra="ignore"` means a client that
    sends `user_id` anyway has it dropped, not stored.
    """
    model_config = ConfigDict(extra="ignore")

    # Only feature views come from the browser. Logins are recorded by the
    # server when the password check passes, so a client cannot inflate them.
    event: Literal["feature_view"]
    feature_key: str = Field(min_length=1, max_length=100)
    account_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class UsageEventBatch(BaseModel):
    events: list[UsageEventIn] = Field(max_length=MAX_EVENTS_PER_BATCH)


class UsageEventBatchResult(BaseModel):
    accepted: int


class FeatureUsage(BaseModel):
    feature_key: str
    unique_users: int
    total_views: int
    last_used_at: datetime | None = None


class UserUsage(BaseModel):
    user_id: str
    email: str
    full_name: str
    is_active: bool
    last_login_at: datetime | None = None
    logins: int
    features_used: int
    top_feature: str | None = None
    # Every feature key, zero included, so the user x feature table has a
    # value in every cell.
    feature_views: dict[str, int]


class DailyActiveUsers(BaseModel):
    date: str          # YYYY-MM-DD, UTC
    active_users: int


class AccountViews(BaseModel):
    account_id: str
    account_name: str | None = None
    views: int
    unique_users: int


class AnalyticsTotals(BaseModel):
    total_users: int
    active_users_7d: int
    logins: int
    feature_views: int


class AnalyticsResponse(BaseModel):
    # Inclusive UTC calendar dates, echoed back so the UI shows what was used.
    date_from: str
    date_to: str
    timezone: Literal["UTC"] = "UTC"
    features: list[str]
    totals: AnalyticsTotals
    per_feature: list[FeatureUsage]
    per_user: list[UserUsage]
    daily_active_users: list[DailyActiveUsers]
    top_accounts: list[AccountViews]
