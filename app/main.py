from typing import Union

from fastapi import FastAPI

from app.api.v3.router import api_router

app = FastAPI(title="SWI MetObs API", version="v3.0.0")

app.include_router(api_router, prefix="/api/v3")
