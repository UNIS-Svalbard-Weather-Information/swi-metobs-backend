from pydantic import BaseModel, field_validator
from typing import List, Literal, Optional
from datetime import datetime
import re


class StationIDModel(BaseModel):
    id: str

    @field_validator("id")
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Invalid station ID format. Only letters, numbers, underscores, and hyphens are allowed."
            )
        return v


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


class StationMetadata(StationIDModel):
    # id: str
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


class StationTimeseries(StationIDModel):
    # station_id: str
    timeseries: List[StationTimeseriesDataPoint]


class StationsAvailableHistoricalDates(StationIDModel):
    # station_id: str
    min_date: str
    max_date: str
    available_dates: List[str]


class DateRangeModel(BaseModel):
    start_date: str
    end_date: str

    @field_validator("start_date", "end_date")
    def validate_iso_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")
        return v


class StationDataRequestModel(StationIDModel):
    start_date: str
    end_date: str
    variables: Optional[List[str]] = None
    resample: bool = False

    @field_validator("start_date", "end_date")
    def validate_iso_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD.")
        return v

    @field_validator("variables", mode="before")
    def validate_variable_names(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
        for var in v:
            if not pattern.match(var):
                raise ValueError(
                    f"Invalid variable name: '{var}'. Only letters, numbers, '_', and '-' are allowed."
                )
        return v
