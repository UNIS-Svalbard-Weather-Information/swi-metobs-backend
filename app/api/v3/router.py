from fastapi import APIRouter
from app.api.v3.endpoints import users, items

api_router = APIRouter()
# api_router.include_router(users.router, prefix="/users", tags=["users"])
# api_router.include_router(items.router, prefix="/items", tags=["items"])
