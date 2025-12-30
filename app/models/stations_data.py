from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional
from datetime import datetime


class StationId(BaseModel):
    id: str


class StationPosition(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None

    @field_validator("lon", "lat")
    @classmethod
    def check_both_or_none(cls, v: Optional[float], info, **kwargs) -> Optional[float]:
        # This validator runs for each field individually, so we need a root validator for cross-field validation.
        # For Pydantic v2, use @model_validator instead of @root_validator.
        return v

    @classmethod
    def validate_both_or_none(cls, values):
        lat = values.get("lat")
        lon = values.get("lon")

        if (lat is None) != (lon is None):
            raise ValueError("lat and lon must both be None or both be float.")
        return values

    @field_validator("lon", "lat", mode="before")
    @classmethod
    def ensure_consistency(cls, v, info, **kwargs):
        # This ensures the values are checked before validation.
        return v

    @classmethod
    def model_validate(cls, data):
        # Custom method to validate the entire model
        lat = data.get("lat")
        lon = data.get("lon")

        if (lat is None) != (lon is None):
            raise ValueError("lat and lon must both be None or both be float.")
        return super().model_validate(data)


class StationMetadata(BaseModel):
    id: str
    name: str
    type: Literal["fixed", "mobile"]
    location: StationPosition
    variables: List[str]
    status: Literal["online", "offline"]
    last_updated: datetime
    project: str
    icon: str


class StationTimeseriesDataPoint(BaseModel):
    timestamp: datetime

    class Config:
        extra = "allow"  # Allow any additional fields


class StationTimeseries(BaseModel):
    station_id: str
    timeseries: List[StationTimeseriesDataPoint]
