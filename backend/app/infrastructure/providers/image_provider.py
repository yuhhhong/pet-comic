import base64
import logging
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from app.domain.errors import AppError
from app.infrastructure.providers.errors import model_call_error

logger = logging.getLogger(__name__)

# 角色卡通过 Images API 的 images.edit 生成，不经过 LangChain。

_SIZES = {"256x256", "512x512", "1024x1024", "1536x1024", "1024x1536", "auto"}
_QUALITIES = {"standard", "low", "medium", "high", "auto"}
_MAX_IMAGE_BYTES = 30 * 1024 * 1024


class ImageProviderAdapter:
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout

    async def edit(self, *, image_paths: list[Path], prompt: str, size: str, quality: str) -> bytes:
        files = [(path.name, path.read_bytes(), _mime(path)) for path in image_paths]
        chosen_size = size if size in _SIZES else "1024x1024"
        chosen_quality = quality if quality in _QUALITIES else "auto"
        if chosen_size != size or chosen_quality != quality:
            logger.warning("image settings size=%s quality=%s are not supported for edit; using defaults", size, quality)
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=0,
        )
        try:
            response = await client.images.edit(
                model=self._model,
                image=files,
                prompt=prompt,
                background="transparent",
                output_format="png",
                size=chosen_size,
                quality=chosen_quality,
                n=1,
            )
        except Exception as exc:
            raise model_call_error(exc, secret=self._api_key, image=True) from exc
        finally:
            await client.close()
        if not response.data:
            raise AppError("IMAGE_GENERATION_FAILED", "角色卡生成失败。", status_code=502, retryable=True)
        image = response.data[0]
        if image.b64_json:
            try:
                return base64.b64decode(image.b64_json)
            except ValueError as exc:
                raise AppError("IMAGE_GENERATION_FAILED", "角色卡生成失败。", status_code=502, retryable=True) from exc
        if image.url and image.url.startswith(("https://", "http://")):
            return await _download(image.url, self._timeout)
        raise AppError("IMAGE_GENERATION_FAILED", "角色卡生成失败。", status_code=502, retryable=True)


async def _download(url: str, timeout: float) -> bytes:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.content
    except httpx.HTTPError as exc:
        raise AppError("IMAGE_GENERATION_FAILED", "角色卡生成失败。", status_code=502, retryable=True) from exc
    if len(data) > _MAX_IMAGE_BYTES:
        raise AppError("IMAGE_GENERATION_FAILED", "生成的角色卡过大。", status_code=502, retryable=True)
    return data


def _mime(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")
