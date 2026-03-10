"""
Health-check route.

GET /health  →  {"status": "ok", "environment": "<current environment>"}
"""

import logging
from fastapi import APIRouter
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Return a simple liveness signal and the current runtime environment."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
