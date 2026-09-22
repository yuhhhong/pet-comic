from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    yield


app = FastAPI(title="Pet Comic API", version="0.1.0", lifespan=lifespan)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
