from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.pets import ArtifactStatus
from app.infrastructure.db.base import utcnow
from app.infrastructure.db.models import PetArtifactModel, PetProfileModel


class PetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, pet_id: str) -> PetProfileModel | None:
        return self.session.get(PetProfileModel, pet_id)

    def get_artifact(self, artifact_id: str) -> PetArtifactModel | None:
        return self.session.get(PetArtifactModel, artifact_id)

    def list_profiles(self, *, status: str | None, trashed: bool) -> list[PetProfileModel]:
        statement = select(PetProfileModel)
        if trashed:
            statement = statement.where(PetProfileModel.deleted_at.is_not(None))
        else:
            statement = statement.where(PetProfileModel.deleted_at.is_(None))
        if status is not None:
            statement = statement.where(PetProfileModel.status == status)
        statement = statement.order_by(PetProfileModel.created_at.desc(), PetProfileModel.pet_id.desc())
        return list(self.session.scalars(statement))

    def artifacts(self, pet_id: str) -> list[PetArtifactModel]:
        statement = (
            select(PetArtifactModel)
            .where(PetArtifactModel.pet_id == pet_id)
            .order_by(PetArtifactModel.kind, PetArtifactModel.version)
        )
        return list(self.session.scalars(statement))

    def artifacts_for(self, pet_ids: list[str]) -> list[PetArtifactModel]:
        if not pet_ids:
            return []
        statement = (
            select(PetArtifactModel)
            .where(PetArtifactModel.pet_id.in_(pet_ids))
            .order_by(PetArtifactModel.pet_id, PetArtifactModel.kind, PetArtifactModel.version)
        )
        return list(self.session.scalars(statement))

    def next_version(self, pet_id: str, kind: str) -> int:
        current = self.session.scalar(
            select(func.max(PetArtifactModel.version)).where(
                PetArtifactModel.pet_id == pet_id,
                PetArtifactModel.kind == kind,
            )
        )
        return int(current or 0) + 1

    def find_succeeded(self, pet_id: str, kind: str, input_hash: str) -> PetArtifactModel | None:
        statement = (
            select(PetArtifactModel)
            .where(
                PetArtifactModel.pet_id == pet_id,
                PetArtifactModel.kind == kind,
                PetArtifactModel.input_hash == input_hash,
                PetArtifactModel.status == ArtifactStatus.SUCCEEDED.value,
            )
            .order_by(PetArtifactModel.version.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def add_artifact(
        self,
        *,
        pet_id: str,
        kind: str,
        version: int,
        path: str | None,
        input_hash: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        retryable: bool | None = None,
        artifact_id: str,
    ) -> PetArtifactModel:
        row = PetArtifactModel(
            artifact_id=artifact_id,
            pet_id=pet_id,
            kind=kind,
            version=version,
            path=path,
            input_hash=input_hash,
            status=status,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            created_at=utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        return row
