import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.pets import router as pets_router
from app.api.providers import router as providers_router
from app.application.provider_service import refresh_enabled_providers
from app.infrastructure.db.app_db import init_db
from app.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.ensure_directories()
    init_db(settings)
    try:
        await refresh_enabled_providers(settings)
    except Exception:
        logger.exception("startup model catalog refresh failed")
    yield


app = FastAPI(title="Pet Comic API", version="0.1.0", lifespan=lifespan)
install_exception_handlers(app)
app.include_router(pets_router)
app.include_router(providers_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
