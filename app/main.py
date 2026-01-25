from fastapi import FastAPI
from app.api.v3.router import api_router
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI(title="SWI MetObs API", version="v3.0.1")

# Read the environment variable for allowed origins
allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/v3")
