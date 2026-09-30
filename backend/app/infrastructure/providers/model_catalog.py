import logging
from dataclasses import dataclass
from datetime import datetime

from openai import AsyncOpenAI

from app.infrastructure.providers.errors import provider_request_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogEntry:
    """一次模型列表刷新的缓存结果；失败时保留错误信息。"""

    model_ids: tuple[str, ...]
    refreshed_at: datetime | None
    error: str | None


class ModelCatalog:
    """按供应商 ID 保存当前进程内的模型列表缓存。"""

    def __init__(self) -> None:
        self._entries: dict[str, CatalogEntry] = {}

    def get(self, provider_id: str) -> CatalogEntry | None:
        return self._entries.get(provider_id)

    def put(self, provider_id: str, entry: CatalogEntry) -> None:
        self._entries[provider_id] = entry

    def forget(self, provider_id: str) -> None:
        self._entries.pop(provider_id, None)


_catalog = ModelCatalog()


def get_model_catalog() -> ModelCatalog:
    return _catalog


async def fetch_remote_models(*, base_url: str, api_key: str, timeout: float) -> tuple[str, ...]:
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
    try:
        page = await client.models.list()
        found: list[str] = []
        for item in page.data:
            model_id = getattr(item, "id", None)
            if isinstance(model_id, str) and model_id.strip():
                found.append(model_id.strip())
    except Exception as exc:
        raise provider_request_error(exc, secret=api_key) from exc
    finally:
        await client.close()
    logger.info("fetched remote models count=%s", len(set(found)))
    return tuple(sorted(set(found), key=str.lower))
