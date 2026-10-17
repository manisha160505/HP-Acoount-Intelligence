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
