from fastapi import APIRouter

from app.api.routes import health
from app.core.config import get_settings

api_v1_router = APIRouter(prefix=get_settings().api_v1_prefix)
# Also under /api/v1 so the frontend reaches it through the same-origin Next.js proxy.
api_v1_router.include_router(health.router)
