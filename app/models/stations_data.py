from pydantic import BaseModel
from typing import List, Literal
from datetime import datetime


class StationId(BaseModel):
    id: str

class StationPosition(BaseModel):
    lat: float
    lon: float

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