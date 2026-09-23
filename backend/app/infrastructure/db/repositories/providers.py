from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.providers import ModelRole
from app.infrastructure.db.models import ModelBindingModel, ProviderModel


@dataclass(frozen=True)
class ResolvedModel:
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
