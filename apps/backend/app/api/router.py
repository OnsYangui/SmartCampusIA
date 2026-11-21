from fastapi import APIRouter

from app.api.routes import auth, catalog, catalog_admin, chat, health, sessions
from app.core.config import get_settings

api_v1_router = APIRouter(prefix=get_settings().api_v1_prefix)
api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(catalog.router)
api_v1_router.include_router(catalog_admin.router)
api_v1_router.include_router(sessions.router)
api_v1_router.include_router(chat.router)
