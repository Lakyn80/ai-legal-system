from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.jurisdictions import router as jurisdictions_router
from app.api.routes.russia import router as russia_router
from app.api.routes.search import router as search_router
from app.api.routes.strategy import router as strategy_router


api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(jurisdictions_router, tags=["jurisdictions"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(documents_router, prefix="/documents", tags=["documents"])
api_router.include_router(search_router, tags=["search"])
api_router.include_router(russia_router, tags=["russia"])
api_router.include_router(strategy_router, prefix="/strategy", tags=["strategy"])
