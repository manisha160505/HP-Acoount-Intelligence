from pydantic import BaseModel
from typing import Literal, Any

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
