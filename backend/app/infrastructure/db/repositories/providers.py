from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.providers import ModelRole
from app.infrastructure.db.base import utcnow
from app.infrastructure.db.models import ModelBindingModel, ProviderModel


@dataclass(frozen=True)
class ResolvedModel:
    """从模型绑定和已启用供应商合成的调用配置。"""

    provider_id: str
    display_name: str
    base_url: str
    api_key: str
    model_id: str
    role: str


class ProviderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve(self, role: ModelRole) -> ResolvedModel | None:
        statement = (
            select(ProviderModel, ModelBindingModel)
            .join(ModelBindingModel, ModelBindingModel.provider_id == ProviderModel.id)
            .where(ModelBindingModel.role == role.value, ProviderModel.enabled.is_(True))
        )
        row = self.session.execute(statement).first()
        if row is None:
            return None
        provider, binding = row
        base_url = provider.base_url.strip()
        api_key = provider.api_key.strip()
        model_id = binding.model_id.strip()
        if not base_url or not api_key or not model_id:
            return None
        return ResolvedModel(
            provider_id=provider.id,
            display_name=provider.display_name,
            base_url=base_url,
            api_key=api_key,
            model_id=model_id,
            role=role.value,
        )

    def missing_roles(self, roles: tuple[ModelRole, ...]) -> list[str]:
        return [role.value for role in roles if self.resolve(role) is None]

    def list_providers(self) -> list[ProviderModel]:
        statement = select(ProviderModel).order_by(ProviderModel.created_at.asc(), ProviderModel.id.asc())
        return list(self.session.scalars(statement))

    def get(self, provider_id: str) -> ProviderModel | None:
        return self.session.get(ProviderModel, provider_id)

    def list_bindings(self) -> list[ModelBindingModel]:
        statement = select(ModelBindingModel).order_by(ModelBindingModel.role.asc())
        return list(self.session.scalars(statement))

    def get_binding(self, role: str) -> ModelBindingModel | None:
        return self.session.get(ModelBindingModel, role)

    def record_refresh(self, provider_id: str, *, error: str | None) -> None:
        provider = self.get(provider_id)
        if provider is None:
            return
        provider.last_model_refresh_at = utcnow()
        provider.last_model_refresh_error = error
        provider.updated_at = provider.last_model_refresh_at
