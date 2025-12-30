from pydantic import BaseModel, field_validator
from typing import List, Optional, Literal
import re

class ForecastFile(BaseModel):
    model: str
    file_path: str
    timestamp: str


ForecastResponse = List[ForecastFile]

class ForecastRequestModel(BaseModel):
    variable: str
    models: Optional[List[str]] = None
    file_type: Literal["cog", "velocity"] = "cog"
    start_hour: int = -24
    end_hour: int = 24

    @field_validator("start_hour", "end_hour")
    def validate_hours(cls, v: int) -> int:
        """Ensure start_hour and end_hour are within a reasonable range."""
        if abs(v) > 168:  # Example: Limit to ±7 days (168 hours)
            raise ValueError("Hour must be between -168 and 168")
        return v

    @field_validator("variable")
    def validate_variable_name(cls, v: str) -> str:
        """Ensure variable name is valid."""
        if not v or not v.strip():
            raise ValueError("Variable cannot be empty")
        pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
        if not pattern.match(v):
            raise ValueError(
                f"Invalid variable name: '{v}'. Only letters, numbers, '_', and '-' are allowed."
            )
        return v.strip()

    @field_validator("models")
    def validate_model_names(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Ensure all model names are valid."""
        if v is None:
            return v
        pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
        for model in v:
            if not model.strip() or not pattern.match(model):
                raise ValueError(
                    f"Invalid model name: '{model}'. Only letters, numbers, '_', and '-' are allowed."
                )
        return v
