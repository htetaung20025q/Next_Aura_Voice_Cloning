from app.api.auth import router as auth_router
from app.api.voice import router as voice_router
from app.api.purchases import router as purchases_router
from app.api.admin import router as admin_router
from app.api.health import router as health_router

__all__ = [
    "auth_router",
    "voice_router",
    "purchases_router",
    "admin_router",
    "health_router",
]
