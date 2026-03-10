"""
Route registry — collect all sub-routers here so main.py has a single import point.
"""

from fastapi import APIRouter

from src.api.routes.auth import router as auth_router
from src.api.routes.health import router as health_router
from src.api.routes.onboarding import router as onboarding_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
