import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.pets import router as pets_router
from app.infrastructure.db.app_db import init_db
from app.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    settings.ensure_directories()
    init_db(settings)
    yield


app = FastAPI(title="Pet Comic API", version="0.1.0", lifespan=lifespan)
install_exception_handlers(app)
app.include_router(pets_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
