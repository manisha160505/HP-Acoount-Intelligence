from typing import Any, Literal

from pydantic import BaseModel


class WidgetContract(BaseModel):
    widget_key: str
    widget_name: str
    feature_key: str
    description: str
    widget_type: str
    data_classification: Literal['deterministic', 'derived', 'inferred']
    source_datasets: list[str]
    source_fields: list[str]
    display_order: int

class WidgetResponse(BaseModel):
    account_id: str
    feature_key: str
    widget_key: str
    widget_name: str
    description: str
    widget_type: str
    data_classification: Literal['deterministic', 'derived', 'inferred']
    status: Literal['available', 'empty', 'pending']
    data: dict[str, Any]
    source_datasets: list[str]
    source_fields: list[str]
    display_order: int
    updated_at: str | None = None

class ContentGenerateRequest(BaseModel):
    persona_id: str
    content_type: str
    topic: str
    additional_context: str = ""
    # The angle the seller picked in the co-creation step. Optional, so a direct
    # generate (no angle chosen) keeps working exactly as before.
    selected_angle: str = ""


class MessageEvaluateRequest(BaseModel):
    persona_contact_id: str
    objective: str
    format: str
    message: str
    mode: str = "DEEP"


class MessageRewriteRequest(BaseModel):
    fingerprint: str
    selected_recommendations: list[str] = []


class StrategyChatMessage(BaseModel):
    role: str          # "user" or "assistant"; anything else is dropped
    content: str


class StrategyChatRequest(BaseModel):
    """One turn of Strategy Chat.

    The whole conversation is sent each time rather than held server-side: the
    chat is stateless per account, and ABX requires prior context to be
    invalidated the moment the selected account changes. A client that switches
    account simply stops sending the old turns.

    `mode` is carried from the start even though only the advisor is
    implemented, so the roleplay personas of Feature 18 can be added later
    without changing this contract.
    """
    messages: list[StrategyChatMessage]
    mode: str = "advisor"
