"""建档生成的数据快照和产物存取；数据库会话不跨越模型请求。"""

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.domain.errors import AppError
from app.domain.pets import ArtifactKind, ArtifactStatus, PetAppearance, PetProfileStatus
from app.domain.providers import ModelRole, missing_provider_error
from app.infrastructure.db.app_db import db_session
from app.infrastructure.db.base import utcnow
from app.infrastructure.db.models import PetArtifactModel
from app.infrastructure.db.repositories.pets import PetRepository
from app.infrastructure.db.repositories.providers import ProviderRepository, ResolvedModel
from app.infrastructure.storage.artifact_store import write_atomic
from app.settings import Settings


@dataclass(frozen=True)
class PetGenerationInput:
    """从数据库读取的建档输入快照，供模型调用使用。"""

    name: str
    personality: str
    species: str
    appearance_json: str | None
    appearance_summary: str | None
    photo_paths: list[Path]


def load_input(settings: Settings, pet_id: str) -> PetGenerationInput | None:
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        if pet is None or pet.deleted_at is not None:
            return None
        return PetGenerationInput(
            name=pet.name,
            personality=pet.personality,
            species=pet.species or "未知",
            appearance_json=pet.appearance_json,
            appearance_summary=pet.appearance_summary,
            photo_paths=_photo_paths(settings, repo.artifacts(pet_id)),
        )


def read_photos(paths: list[Path]) -> list[bytes]:
    try:
        return [path.read_bytes() for path in paths]
    except OSError as exc:
        raise AppError("VALIDATION_ERROR", "证件照文件丢失或无法读取，请重新建档。", status_code=422) from exc


def resolve_model(role: ModelRole) -> ResolvedModel:
    with db_session() as session:
        binding = ProviderRepository(session).resolve(role)
    if binding is None:
        raise missing_provider_error([role.value])
    return binding


def has_saved_appearance(pet_id: str, input_hash: str) -> bool:
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        existing = repo.find_succeeded(pet_id, ArtifactKind.APPEARANCE.value, input_hash)
        return existing is not None and pet is not None and bool(pet.appearance_json)


def has_saved_character_card(settings: Settings, pet_id: str, input_hash: str) -> bool:
    with db_session() as session:
        existing = PetRepository(session).find_succeeded(pet_id, ArtifactKind.CHARACTER_CARD.value, input_hash)
        return existing is not None and existing.path is not None and (settings.data_dir / existing.path).is_file()


def save_appearance(settings: Settings, pet_id: str, input_hash: str, appearance: PetAppearance) -> None:
    payload = appearance.model_dump()
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    relative = f"pets/{pet_id}/appearance.json"
    write_atomic(settings.data_dir / relative, raw)
    with db_session() as session:
        repo = PetRepository(session)
        repo.add_artifact(
            pet_id=pet_id,
            kind=ArtifactKind.APPEARANCE.value,
            version=repo.next_version(pet_id, ArtifactKind.APPEARANCE.value),
            path=relative,
            input_hash=input_hash,
            status=ArtifactStatus.SUCCEEDED.value,
            artifact_id=str(uuid4()),
        )
        pet = repo.get(pet_id)
        if pet is not None:
            pet.species = appearance.species
            pet.appearance_json = json.dumps(payload, ensure_ascii=False)
            pet.appearance_summary = appearance.summary
            pet.updated_at = utcnow()


def save_character_card(settings: Settings, pet_id: str, input_hash: str, png: bytes) -> None:
    with db_session() as session:
        repo = PetRepository(session)
        version = repo.next_version(pet_id, ArtifactKind.CHARACTER_CARD.value)
        relative = f"pets/{pet_id}/character-cards/v{version:03d}.png"
        write_atomic(settings.data_dir / relative, png)
        repo.add_artifact(
            pet_id=pet_id,
            kind=ArtifactKind.CHARACTER_CARD.value,
            version=version,
            path=relative,
            input_hash=input_hash,
            status=ArtifactStatus.SUCCEEDED.value,
            artifact_id=str(uuid4()),
        )
        pet = repo.get(pet_id)
        if pet is not None:
            pet.updated_at = utcnow()


def record_failure(pet_id: str, *, kind: ArtifactKind, input_hash: str, error: AppError) -> None:
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        if pet is None:
            return
        repo.add_artifact(
            pet_id=pet_id,
            kind=kind.value,
            version=repo.next_version(pet_id, kind.value),
            path=None,
            input_hash=input_hash,
            status=ArtifactStatus.FAILED.value,
            error_code=error.code,
            error_message=error.message,
            retryable=error.retryable,
            artifact_id=str(uuid4()),
        )
        pet.updated_at = utcnow()


def finalize_profile(settings: Settings, pet_id: str) -> None:
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        if pet is None or pet.deleted_at is not None:
            return
        card = _usable_character_card(settings, repo.artifacts(pet_id))
        if card is not None:
            pet.active_character_card_id = card.artifact_id
            if pet.status != PetProfileStatus.DISABLED.value:
                pet.status = PetProfileStatus.READY.value
        elif pet.status != PetProfileStatus.DISABLED.value:
            pet.status = PetProfileStatus.DRAFT.value
            pet.active_character_card_id = None
        pet.updated_at = utcnow()


def _photo_paths(settings: Settings, artifacts: list[PetArtifactModel]) -> list[Path]:
    photos = [
        item for item in artifacts
        if item.kind == ArtifactKind.ID_PHOTO.value and item.status == ArtifactStatus.SUCCEEDED.value and item.path
    ]
    photos.sort(key=lambda item: item.version)
    return [settings.data_dir / item.path for item in photos if item.path is not None]


def _usable_character_card(settings: Settings, artifacts: list[PetArtifactModel]) -> PetArtifactModel | None:
    cards = [
        item for item in artifacts
        if item.kind == ArtifactKind.CHARACTER_CARD.value and item.status == ArtifactStatus.SUCCEEDED.value
        and item.path and (settings.data_dir / item.path).is_file()
    ]
    return max(cards, key=lambda item: item.version) if cards else None
