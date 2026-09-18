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
    # `partial` is what the urgency score writes when it computed what it could
    # but some inputs were missing (`urgency.py`: "available" if not
    # missing_inputs else "partial"), and it was absent from this literal.
    #
    # The consequence was not a bad field, it was a blank feature. FastAPI
    # validates the WHOLE response array, so one widget carrying an unlisted
    # status made `GET /accounts/{id}/widgets/executive_dashboard` return 500 -
    # and the frontend's fetch swallows a failure non-blockingly, so every panel
    # rendered its "no data yet" placeholder while the data sat in Mongo intact.
    # An account whose urgency score could not be computed lost its company
    # profile, its metrics and its priorities too.
    #
    # Added rather than removed from the writer: "computed, but on incomplete
    # inputs" is a real state and worth telling a seller apart from "not
    # computed". Anything that ever writes a fourth status must come here too.
    status: Literal['available', 'empty', 'pending', 'partial']
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

    `mode` was carried from the start so the roleplay personas could be added
    without breaking this contract, and they were: `persona_id` is optional and
    every existing client keeps working untouched.

    `mode` is a Literal rather than the bare `str` it began as. As a free string
    a client typo - "Roleplay", "roleplay " - silently produced advisor
    behaviour while echoing the typo back, so a seller could believe they were
    rehearsing while talking to the advisor. A 422 is the better answer.
    """
    messages: list[StrategyChatMessage]
    mode: Literal["advisor", "roleplay"] = "advisor"
    # Which stakeholder to play. Required for roleplay and rejected for
    # advisor - see the endpoint, which refuses rather than falling back.
    persona_id: str | None = None
