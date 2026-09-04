from pydantic import BaseModel
from typing import Literal

class MappedField(BaseModel):
    field_key: str
    display_name: str
    purpose: str
    dataset_key: str | None
    source_sheet: str | None
    source_column: str | None
    data_type: Literal['DETERMINISTIC', 'INFERRED / SYNTHESIZED']

class FeatureMappingResponse(BaseModel):
    feature_key: str
    display_name: str
    purpose: str
    dependent_datasets: list[str]
    mapped_fields: list[MappedField]

class ReverseDependencyResponse(BaseModel):
    dataset_key: str
    display_name: str
    mapped_features: list[str]
    is_mapped: bool
