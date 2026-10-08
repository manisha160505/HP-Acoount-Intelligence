from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError('Account name cannot be empty or whitespace only')
        return trimmed

class AccountCreate(AccountBase):
    pass

class AccountStatusUpdate(BaseModel):
    status: Literal['active', 'hidden']

class AccountResponse(BaseModel):
    id: str
    name: str
    status: Literal['active', 'hidden']
    created_at: str
    updated_at: str
    # Feature keys hidden for this account (config/account_overrides.yaml).
    hidden_features: list[str] = []


class UserAccountResponse(AccountResponse):
    # The account's published urgency score, read from the committed
    # `exec_urgency_score` widget - the same value the Executive Dashboard
    # shows. None when the widget has not been generated or the score was
    # withheld for low coverage.
    urgency_score: int | None = None
    urgency_max_score: int | None = None
