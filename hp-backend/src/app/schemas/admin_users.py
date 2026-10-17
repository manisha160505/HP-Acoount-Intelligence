from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Roles an admin screen can give. There is one super admin, made by a script;
# no request can create or remove one.
AssignableRole = Literal["user", "admin"]


class AdminUserCreate(BaseModel):
    """What an admin sends to add a user.

    `role` "admin" is honoured only from the super admin. `password` left out
    means the server generates one and returns it once, in the response.
    `full_name` left out means the email stands in for it."""
    email: EmailStr
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: AssignableRole = "user"
    account_ids: list[str] = Field(default_factory=list, max_length=1000)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserStatusUpdate(BaseModel):
    """The only thing PATCH may change: role, accounts and password each have
    their own endpoint, so each can carry its own permission check."""
    is_active: bool


class RoleUpdate(BaseModel):
    role: AssignableRole


class AccountAssignment(BaseModel):
    account_ids: list[str] = Field(max_length=1000)


class PasswordResetRequest(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)


class AdminUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool = False
    account_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class AdminUserCreated(AdminUserResponse):
    # Present only when the server generated it. Shown to the admin once and
    # stored nowhere but as a hash.
    temporary_password: str | None = None


class PasswordResetResponse(BaseModel):
    user: AdminUserResponse
    temporary_password: str | None = None


class AccountUser(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool


class AuditEntry(BaseModel):
    id: str
    ts: datetime
    actor_email: str | None = None
    action: str
    target_email: str | None = None
    details: dict = Field(default_factory=dict)
