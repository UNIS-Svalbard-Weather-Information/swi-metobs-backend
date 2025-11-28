from pydantic import BaseModel
from typing import List, Optional


class ForecastFile(BaseModel):
    model: str
    file_path: str
    timestamp: str


ForecastResponse = List[ForecastFile]
