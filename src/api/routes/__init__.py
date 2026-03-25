"""
Route registry — collect all sub-routers here so main.py has a single import point.
"""

from fastapi import APIRouter

from src.api.routes.admin import router as admin_router
from src.api.routes.auth import router as auth_router
from src.api.routes.briefs import router as briefs_router
from src.api.routes.calendar import router as calendar_router
from src.api.routes.chat import router as chat_router
from src.api.routes.commitments import router as commitments_router
from src.api.routes.conversations import router as conversations_router
from src.api.routes.entities import router as entities_router
from src.api.routes.graph import router as graph_router
from src.api.routes.health import router as health_router
from src.api.routes.home import router as home_router
from src.api.routes.index_stats import router as index_stats_router
from src.api.routes.onboarding import router as onboarding_router
from src.api.routes.search import router as search_router
from src.api.routes.topics import router as topics_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
router.include_router(conversations_router, prefix="/conversations", tags=["conversations"])
router.include_router(search_router, prefix="/search", tags=["search"])
router.include_router(briefs_router, prefix="/briefs", tags=["briefs"])
router.include_router(topics_router, prefix="/topics", tags=["topics"])
router.include_router(commitments_router, prefix="/commitments", tags=["commitments"])
router.include_router(entities_router, prefix="/entities", tags=["entities"])
router.include_router(graph_router, prefix="/graph", tags=["graph"])
router.include_router(index_stats_router, prefix="/index", tags=["index"])
router.include_router(calendar_router, prefix="/calendar", tags=["calendar"])
router.include_router(home_router, prefix="/home", tags=["home"])
router.include_router(chat_router, prefix="/chat", tags=["chat"])
router.include_router(admin_router, prefix="/admin", tags=["admin"])
