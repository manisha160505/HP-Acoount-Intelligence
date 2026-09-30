from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminUserCreate(BaseModel):
    """What an admin sends to add a user. There is deliberately no `role`:
    this endpoint only ever creates role `user`, and a stray `role` in the
    body is ignored rather than honoured."""
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)


class AdminUserStatusUpdate(BaseModel):
    """The only thing PATCH may change."""
    is_active: bool


class AdminUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None
