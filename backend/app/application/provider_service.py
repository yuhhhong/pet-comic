import logging
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.domain.errors import AppError
from app.domain.providers import (
    ModelBindingSet,
    ModelBindingView,
    ModelRole,
    ProviderView,
    RemoteModelList,
    mask_api_key,
)
from app.infrastructure.db.app_db import db_session
from app.infrastructure.db.base import ensure_utc, utcnow
from app.infrastructure.db.models import ModelBindingModel, ProviderModel
from app.infrastructure.db.repositories.providers import ProviderRepository
from app.infrastructure.providers import model_catalog
from app.infrastructure.providers.model_catalog import CatalogEntry
from app.settings import Settings

logger = logging.getLogger(__name__)

_NAME_LIMIT = 60
_URL_LIMIT = 300
_KEY_LIMIT = 2000


class ProviderService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = ProviderRepository(session)

    def list_providers(self) -> list[ProviderView]:
        return [self._view(provider) for provider in self.repo.list_providers()]

    def get(self, provider_id: str) -> ProviderView:
        return self._view(self._require(provider_id))

    async def create(self, *, display_name: str, base_url: str, api_key: str, enabled: bool) -> ProviderView:
        provider = ProviderModel(
            id=str(uuid4()),
            display_name=_clean_name(display_name),
            base_url=_clean_base_url(base_url),
            api_key=_clean_api_key(api_key),
            enabled=enabled,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.session.add(provider)
        self.session.commit()
        if enabled:
            await refresh_provider_models(
                provider.id,
                base_url=provider.base_url,
                api_key=provider.api_key,
                timeout=self.settings.request_timeout_seconds,
                raise_error=False,
            )
        self.session.expire_all()
        return self._view(self._require(provider.id))

    async def update(
        self,
        provider_id: str,
        *,
        display_name: str | None,
        base_url: str | None,
        api_key: str | None,
        enabled: bool | None,
    ) -> ProviderView:
        if display_name is None and base_url is None and api_key is None and enabled is None:
            raise AppError("VALIDATION_ERROR", "没有要更新的内容。", status_code=422)
        provider = self._require(provider_id)
        was_enabled = provider.enabled
        credentials_changed = False
        if display_name is not None:
            provider.display_name = _clean_name(display_name)
        if base_url is not None:
            provider.base_url = _clean_base_url(base_url)
            credentials_changed = True
        if api_key is not None:
            provider.api_key = _clean_api_key(api_key)
            credentials_changed = True
        if enabled is not None:
            provider.enabled = enabled
        provider.updated_at = utcnow()
        became_enabled = provider.enabled and not was_enabled
        provider_key = provider.api_key
        provider_url = provider.base_url
        saved_id = provider.id
        should_refresh = provider.enabled and (credentials_changed or became_enabled)
        self.session.commit()
        if not provider.enabled:
            model_catalog.get_model_catalog().forget(saved_id)
        elif should_refresh:
            await refresh_provider_models(
                saved_id,
                base_url=provider_url,
                api_key=provider_key,
                timeout=self.settings.request_timeout_seconds,
                raise_error=False,
            )
        self.session.expire_all()
        return self._view(self._require(saved_id))

    async def refresh(self, provider_id: str) -> ProviderView:
        provider = self._require(provider_id)
        saved_id = provider.id
        base_url = provider.base_url
        api_key = provider.api_key
        await refresh_provider_models(
            saved_id,
            base_url=base_url,
            api_key=api_key,
            timeout=self.settings.request_timeout_seconds,
            raise_error=True,
        )
        self.session.expire_all()
        return self._view(self._require(saved_id))

    def list_models(self, provider_id: str) -> RemoteModelList:
        provider = self._require(provider_id)
        entry = model_catalog.get_model_catalog().get(provider.id)
        if entry is None:
            return RemoteModelList(
                provider_id=provider.id,
                models=[],
                refreshed_at=None,
                error=provider.last_model_refresh_error,
            )
        return RemoteModelList(
            provider_id=provider.id,
            models=list(entry.model_ids),
            refreshed_at=ensure_utc(entry.refreshed_at) if entry.refreshed_at else None,
            error=entry.error,
        )

    def get_bindings(self) -> ModelBindingSet:
        return _binding_set(self.repo.list_bindings(), {provider.id: provider for provider in self.repo.list_providers()})

    def update_bindings(
        self,
        *,
        vision: tuple[str, str] | None,
        script: tuple[str, str] | None,
        image: tuple[str, str] | None,
    ) -> ModelBindingSet:
        incoming = {
            ModelRole.VISION.value: vision,
            ModelRole.SCRIPT.value: script,
            ModelRole.IMAGE.value: image,
        }
        validated = {role: self._validate_binding(value) for role, value in incoming.items()}
        for role, value in validated.items():
            current = self.repo.get_binding(role)
            if value is None:
                if current is not None:
                    self.session.delete(current)
                continue
            provider_id, model_id = value
            if current is None:
                self.session.add(
                    ModelBindingModel(role=role, provider_id=provider_id, model_id=model_id, updated_at=utcnow())
                )
            else:
                current.provider_id = provider_id
                current.model_id = model_id
                current.updated_at = utcnow()
        self.session.commit()
        self.session.expire_all()
        return self.get_bindings()

    def _validate_binding(self, value: tuple[str, str] | None) -> tuple[str, str] | None:
        if value is None:
            return None
        provider_id, model_id = value
        provider = self._require(provider_id)
        if not provider.enabled:
            raise AppError("PROVIDER_DISABLED", "这个供应商已停用，不能绑定。", status_code=409)
        cleaned_model = model_id.strip()
        if not cleaned_model or len(cleaned_model) > 200:
            raise AppError("VALIDATION_ERROR", "请选择一个模型。", status_code=422)
        entry = model_catalog.get_model_catalog().get(provider.id)
        if entry is None or entry.error or cleaned_model not in entry.model_ids:
            raise AppError(
                "MODEL_NOT_IN_CATALOG",
                "模型列表里没有这个模型，请先刷新。",
                status_code=422,
                details={"provider_id": provider.id, "model_id": cleaned_model},
            )
        return provider.id, cleaned_model

    def _require(self, provider_id: str) -> ProviderModel:
        try:
            normalized = str(UUID(provider_id))
        except ValueError as exc:
            raise AppError("PROVIDER_NOT_FOUND", "没有找到这个供应商。", status_code=404) from exc
        provider = self.repo.get(normalized)
        if provider is None:
            raise AppError("PROVIDER_NOT_FOUND", "没有找到这个供应商。", status_code=404)
        return provider

    def _view(self, provider: ProviderModel) -> ProviderView:
        has_key, hint = mask_api_key(provider.api_key)
        return ProviderView(
            id=provider.id,
            display_name=provider.display_name,
            base_url=provider.base_url,
            enabled=provider.enabled,
            has_api_key=has_key,
            api_key_hint=hint,
            last_model_refresh_at=ensure_utc(provider.last_model_refresh_at) if provider.last_model_refresh_at else None,
            last_model_refresh_error=provider.last_model_refresh_error,
            created_at=ensure_utc(provider.created_at),
            updated_at=ensure_utc(provider.updated_at),
        )


async def refresh_enabled_providers(settings: Settings) -> None:
    with db_session() as session:
        snapshots = [
            (provider.id, provider.base_url, provider.api_key)
            for provider in ProviderRepository(session).list_providers()
            if provider.enabled and provider.base_url.strip() and provider.api_key.strip()
        ]
    for provider_id, base_url, api_key in snapshots:
        await refresh_provider_models(
            provider_id,
            base_url=base_url,
            api_key=api_key,
            timeout=settings.request_timeout_seconds,
            raise_error=False,
        )


async def refresh_provider_models(
    provider_id: str,
    *,
    base_url: str,
    api_key: str,
    timeout: float,
    raise_error: bool,
) -> None:
    catalog = model_catalog.get_model_catalog()
    try:
        model_ids = await model_catalog.fetch_remote_models(base_url=base_url, api_key=api_key, timeout=timeout)
    except AppError as exc:
        message = _scrub(exc.message, api_key)
        catalog.put(provider_id, CatalogEntry(model_ids=(), refreshed_at=None, error=message))
        _record_refresh(provider_id, error=message)
        logger.warning("model catalog refresh failed provider_id=%s code=%s", provider_id, exc.code)
        if raise_error:
            raise AppError(exc.code, message, status_code=exc.status_code, details=exc.details, retryable=exc.retryable) from None
        return
    except Exception as exc:
        logger.warning("model catalog refresh crashed provider_id=%s error_type=%s", provider_id, type(exc).__name__)
        message = "无法获取模型列表。"
        catalog.put(provider_id, CatalogEntry(model_ids=(), refreshed_at=None, error=message))
        _record_refresh(provider_id, error=message)
        if raise_error:
            raise AppError("PROVIDER_REQUEST_FAILED", message, status_code=502, retryable=True) from None
        return
    refreshed_at = utcnow()
    catalog.put(provider_id, CatalogEntry(model_ids=model_ids, refreshed_at=refreshed_at, error=None))
    _record_refresh(provider_id, error=None)


def _record_refresh(provider_id: str, *, error: str | None) -> None:
    with db_session() as session:
        ProviderRepository(session).record_refresh(provider_id, error=error)


def _binding_set(bindings: list[ModelBindingModel], providers: dict[str, ProviderModel]) -> ModelBindingSet:
    found = {binding.role: binding for binding in bindings}

    def view(role: ModelRole) -> ModelBindingView | None:
        binding = found.get(role.value)
        if binding is None:
            return None
        provider = providers.get(binding.provider_id)
        return ModelBindingView(
            provider_id=binding.provider_id,
            provider_name=provider.display_name if provider else "已删除的供应商",
            model_id=binding.model_id,
            provider_enabled=bool(provider and provider.enabled),
        )

    return ModelBindingSet(vision=view(ModelRole.VISION), script=view(ModelRole.SCRIPT), image=view(ModelRole.IMAGE))


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise AppError("VALIDATION_ERROR", "请填写供应商名称。", status_code=422, details={"field": "display_name"})
    if len(name) > _NAME_LIMIT:
        raise AppError("VALIDATION_ERROR", "供应商名称不能超过 60 个字。", status_code=422, details={"field": "display_name"})
    return name


def _clean_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or len(url) > _URL_LIMIT:
        raise AppError(
            "VALIDATION_ERROR",
            "供应商地址需要是包含 /v1 的 HTTP 或 HTTPS 地址。",
            status_code=422,
            details={"field": "base_url"},
        )
    return url


def _clean_api_key(value: str) -> str:
    key = value.strip()
    if not key or any(character.isspace() for character in key) or len(key) > _KEY_LIMIT:
        raise AppError("VALIDATION_ERROR", "请填写有效的 API Key。", status_code=422, details={"field": "api_key"})
    return key


def _scrub(message: str, secret: str) -> str:
    if secret:
        message = message.replace(secret, "***")
    return message[:500]
