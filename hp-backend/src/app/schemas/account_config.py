from datetime import datetime
from pydantic import BaseModel, Field

class AccountInstructionsUpdate(BaseModel):
    instructions_text: str = Field(default="")

class AccountInstructionsResponse(BaseModel):
    account_id: str
    instructions_text: str
    updated_at: str

class AccountGuardrailsUpdate(BaseModel):
    enabled: bool = Field(default=False)
    guardrails_text: str = Field(default="")

class AccountGuardrailsResponse(BaseModel):
    account_id: str
    enabled: bool
    guardrails_text: str
    updated_at: str
