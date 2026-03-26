from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.dependencies import get_embedding_service, get_qdrant_vector_store
from app.core.logging import configure_logging


settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def validate_embedding_runtime() -> None:
    embedding_service = get_embedding_service()
    vector_store = get_qdrant_vector_store()
    vector_store.ensure_active_collection(embedding_service.profile)


app.include_router(api_router, prefix=settings.api_prefix)
