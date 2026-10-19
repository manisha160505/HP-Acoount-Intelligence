from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str

class UserResponse(UserBase):
    id: str
    # True until the user replaces the password an admin gave them; the
    # frontend sends them to the change-password page and nowhere else.
    must_change_password: bool = False
    # When the user finished or closed the first-sign-in tour; None until
    # then, and the dashboard starts the tour while it is None.
    tour_completed_at: datetime | None = None
    # The same for the admin pages' tour (Accounts, Platform, Users,
    # Analytics), kept apart so an admin sees each tour once.
    admin_tour_completed_at: datetime | None = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Seconds until access_token expires; the frontend refreshes before then.
    expires_in: int
    user: UserResponse

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)

class TourCompletedResponse(BaseModel):
    tour: str
    tour_completed_at: datetime


class ChangePasswordResponse(BaseModel):
    message: str
    # Shown once: the code that lets this user set a new password themselves.
    recovery_code: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    recovery_code: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=1, max_length=128)
