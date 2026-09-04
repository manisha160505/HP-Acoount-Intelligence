from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Literal

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
