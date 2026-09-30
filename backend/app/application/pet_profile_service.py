import logging
import shutil
from collections import defaultdict
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain.errors import AppError
from app.domain.pets import (
    LEGACY_RETRYABLE_ERROR_CODES,
    ArtifactKind,
    ArtifactStatus,
    PetAppearance,
    PetArtifactView,
    PetDetail,
    PetErrorView,
    PetProfileStatus,
    PetSummary,
    normalize_name,
    normalize_personality,
)
from app.domain.providers import ModelRole, missing_provider_error
from app.infrastructure.db.base import ensure_utc, utcnow
from app.infrastructure.db.models import PetArtifactModel, PetProfileModel
from app.infrastructure.db.repositories.pets import PetRepository
from app.infrastructure.db.repositories.providers import ProviderRepository
from app.infrastructure.storage.artifact_store import digest, pet_relative_path
from app.infrastructure.storage.image_inputs import StoredPhoto, save_id_photos, validate_id_photos
from app.settings import Settings
from app.workflow.graph import get_pet_profile_graph

logger = logging.getLogger(__name__)


class PetProfileService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = PetRepository(session)

    async def create(self, *, name: str, personality: str, photos: list[tuple[str, bytes]]) -> PetDetail:
        clean_name = normalize_name(name)
        clean_personality = normalize_personality(personality)
        validated = validate_id_photos(photos, self.settings.max_image_size_mb)
        self._ensure_generation_models()
        pet_id = str(uuid4())
        pet_dir = self.settings.pet_dir / pet_id
        try:
            stored = save_id_photos(self.settings, pet_id, validated)
            self._insert_draft(pet_id, clean_name, clean_personality, stored)
            # 工作流使用独立会话，调用模型前必须先提交档案和证件照记录。
            self.session.commit()
        except Exception:
            self.session.rollback()
            shutil.rmtree(pet_dir, ignore_errors=True)
            raise
        await self._execute(pet_id, force_character_card=False)
        return self._detail(pet_id)

    def list_profiles(self, *, status: PetProfileStatus | None, trashed: bool) -> list[PetSummary]:
        pets = self.repo.list_profiles(status=status.value if status else None, trashed=trashed)
        grouped: dict[str, list[PetArtifactModel]] = defaultdict(list)
        for artifact in self.repo.artifacts_for([pet.pet_id for pet in pets]):
            grouped[artifact.pet_id].append(artifact)
        return [self._summary(pet, grouped[pet.pet_id]) for pet in pets]

    def get(self, pet_id: str) -> PetDetail:
        pet = self._require(pet_id, allow_deleted=True)
        return self._detail(pet.pet_id)

    async def update(
        self,
        pet_id: str,
        *,
        name: str | None,
        personality: str | None,
        enabled: bool | None,
    ) -> PetDetail:
        if name is None and personality is None and enabled is None:
            raise AppError("VALIDATION_ERROR", "没有要更新的内容。", status_code=422)
        pet = self._require(pet_id)
        if name is not None:
            pet.name = normalize_name(name)
        if personality is not None:
            pet.personality = normalize_personality(personality)
        if enabled is not None:
            self._set_enabled(pet, enabled)
        pet.updated_at = utcnow()
        self.session.commit()
        return self._detail(pet.pet_id)

    async def retry(self, pet_id: str) -> PetDetail:
        pet = self._require(pet_id)
        await self._execute(pet.pet_id, force_character_card=False)
        return self._detail(pet.pet_id)

    async def retry_character_card(self, pet_id: str) -> PetDetail:
        pet = self._require(pet_id)
        if not pet.appearance_json:
            raise AppError("APPEARANCE_REQUIRED", "外观还没有提取成功，不能单独生成角色卡。", status_code=409)
        await self._execute(pet.pet_id, force_character_card=True)
        return self._detail(pet.pet_id)

    def trash(self, pet_id: str) -> PetDetail:
        pet = self._require(pet_id, allow_deleted=True)
        if pet.deleted_at is None:
            now = utcnow()
            pet.deleted_at = now
            pet.updated_at = now
            self.session.commit()
        return self._detail(pet.pet_id)

    def delete(self, pet_id: str) -> None:
        pet = self._require(pet_id, allow_deleted=True)
        self.session.execute(delete(PetArtifactModel).where(PetArtifactModel.pet_id == pet.pet_id))
        self.session.delete(pet)
        self.session.commit()

    def resolve_file(self, pet_id: str, file_path: str) -> Path:
        pet = self._require(pet_id, allow_deleted=True)
        relative = _safe_relative(file_path)
        expected = f"pets/{pet.pet_id}/{relative}"
        match = next(
            (
                artifact
                for artifact in self.repo.artifacts(pet.pet_id)
                if artifact.path == expected and artifact.status == ArtifactStatus.SUCCEEDED.value
            ),
            None,
        )
        if match is None:
            raise AppError("PET_NOT_FOUND", "没有找到这张图片。", status_code=404)
        path = (self.settings.data_dir / expected).resolve()
        root = (self.settings.pet_dir / pet.pet_id).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise AppError("PET_NOT_FOUND", "没有找到这张图片。", status_code=404)
        return path

    async def _execute(self, pet_id: str, *, force_character_card: bool) -> None:
        try:
            await get_pet_profile_graph().ainvoke(
                {
                    "pet_id": pet_id,
                    "force_character_card": force_character_card,
                    "error_code": None,
                    "error_message": None,
                    "retryable": False,
                }
            )
        except Exception:
            logger.exception("pet profile graph crashed pet_id=%s", pet_id)
            self._record_crash(pet_id)
        self.session.expire_all()

    def _record_crash(self, pet_id: str) -> None:
        self.session.expire_all()
        pet = self.repo.get(pet_id)
        if pet is None or pet.status == PetProfileStatus.READY.value:
            return
        relevant = [
            artifact
            for artifact in self.repo.artifacts(pet_id)
            if artifact.kind in {ArtifactKind.APPEARANCE.value, ArtifactKind.CHARACTER_CARD.value}
        ]
        if relevant:
            latest = max(relevant, key=lambda item: (item.created_at, item.version))
            if latest.status == ArtifactStatus.FAILED.value:
                return
        self.repo.add_artifact(
            pet_id=pet_id,
            kind=ArtifactKind.APPEARANCE.value,
            version=self.repo.next_version(pet_id, ArtifactKind.APPEARANCE.value),
            path=None,
            input_hash=digest(b"internal-error"),
            status=ArtifactStatus.FAILED.value,
            error_code="INTERNAL_ERROR",
            error_message="建档过程中断，请重试。",
            retryable=True,
            artifact_id=str(uuid4()),
        )
        pet.updated_at = utcnow()
        self.session.commit()

    def _ensure_generation_models(self) -> None:
        missing = ProviderRepository(self.session).missing_roles((ModelRole.VISION, ModelRole.IMAGE))
        if missing:
            raise missing_provider_error(missing)

    def _insert_draft(self, pet_id: str, name: str, personality: str, photos: list[StoredPhoto]) -> None:
        now = utcnow()
        self.session.add(
            PetProfileModel(
                pet_id=pet_id,
                name=name,
                personality=personality,
                species=None,
                appearance_json=None,
                appearance_summary=None,
                status=PetProfileStatus.DRAFT.value,
                active_character_card_id=None,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.flush()
        for version, photo in enumerate(photos, start=1):
            self.repo.add_artifact(
                pet_id=pet_id,
                kind=ArtifactKind.ID_PHOTO.value,
                version=version,
                path=photo.path,
                input_hash=photo.input_hash,
                status=ArtifactStatus.SUCCEEDED.value,
                artifact_id=str(uuid4()),
            )

    def _require(self, pet_id: str, *, allow_deleted: bool = False) -> PetProfileModel:
        try:
            normalized = str(UUID(pet_id))
        except ValueError as exc:
            raise AppError("PET_NOT_FOUND", "没有找到这只宠物。", status_code=404) from exc
        pet = self.repo.get(normalized)
        if pet is None:
            raise AppError("PET_NOT_FOUND", "没有找到这只宠物。", status_code=404)
        if pet.deleted_at is not None and not allow_deleted:
            raise AppError("PET_DELETED", "这只宠物已在回收区。", status_code=409)
        return pet

    def _set_enabled(self, pet: PetProfileModel, enabled: bool) -> None:
        status = PetProfileStatus(pet.status)
        if enabled:
            if status is PetProfileStatus.READY:
                return
            if status is PetProfileStatus.DISABLED and self._has_usable_card(pet):
                pet.status = PetProfileStatus.READY.value
                return
            message = "角色卡文件不存在，不能启用。" if status is PetProfileStatus.DISABLED else "角色卡还没有生成，不能启用。"
            raise AppError("PET_STATUS_CONFLICT", message, status_code=409)
        if status is PetProfileStatus.DISABLED:
            return
        if status is not PetProfileStatus.READY:
            raise AppError("PET_STATUS_CONFLICT", "只有可用档案可以停用。", status_code=409)
        pet.status = PetProfileStatus.DISABLED.value

    def _has_usable_card(self, pet: PetProfileModel) -> bool:
        if not pet.active_character_card_id:
            return False
        card = self.repo.get_artifact(pet.active_character_card_id)
        return bool(
            card
            and card.status == ArtifactStatus.SUCCEEDED.value
            and card.path
            and (self.settings.data_dir / card.path).is_file()
        )

    def _detail(self, pet_id: str) -> PetDetail:
        pet = self.repo.get(pet_id)
        if pet is None:
            raise AppError("PET_NOT_FOUND", "没有找到这只宠物。", status_code=404)
        artifacts = self.repo.artifacts(pet_id)
        photos = [item for item in artifacts if item.kind == ArtifactKind.ID_PHOTO.value]
        cards = [item for item in artifacts if item.kind == ArtifactKind.CHARACTER_CARD.value]
        cards.sort(key=lambda item: item.version, reverse=True)
        return PetDetail(
            pet_id=pet.pet_id,
            name=pet.name,
            personality=pet.personality,
            species=pet.species,
            appearance=_appearance(pet.appearance_json),
            appearance_summary=pet.appearance_summary,
            status=PetProfileStatus(pet.status),
            active_character_card_id=pet.active_character_card_id,
            id_photos=[_artifact_view(pet.pet_id, item) for item in photos],
            character_cards=[_artifact_view(pet.pet_id, item) for item in cards],
            error=_current_error(artifacts),
            deleted_at=ensure_utc(pet.deleted_at) if pet.deleted_at else None,
            created_at=ensure_utc(pet.created_at),
            updated_at=ensure_utc(pet.updated_at),
        )

    def _summary(self, pet: PetProfileModel, artifacts: list[PetArtifactModel]) -> PetSummary:
        return PetSummary(
            pet_id=pet.pet_id,
            name=pet.name,
            personality=pet.personality,
            species=pet.species,
            appearance_summary=pet.appearance_summary,
            status=PetProfileStatus(pet.status),
            thumbnail_path=_thumbnail(pet, artifacts),
            deleted_at=ensure_utc(pet.deleted_at) if pet.deleted_at else None,
            created_at=ensure_utc(pet.created_at),
            updated_at=ensure_utc(pet.updated_at),
        )


def _artifact_view(pet_id: str, artifact: PetArtifactModel) -> PetArtifactView:
    return PetArtifactView(
        artifact_id=artifact.artifact_id,
        kind=ArtifactKind(artifact.kind),
        version=artifact.version,
        path=pet_relative_path(pet_id, artifact.path),
        status=ArtifactStatus(artifact.status),
        error_code=artifact.error_code,
        created_at=ensure_utc(artifact.created_at),
    )


def _current_error(artifacts: list[PetArtifactModel]) -> PetErrorView | None:
    relevant = [
        artifact
        for artifact in artifacts
        if artifact.kind in {ArtifactKind.APPEARANCE.value, ArtifactKind.CHARACTER_CARD.value}
    ]
    if not relevant:
        return None
    latest = max(relevant, key=lambda item: (item.created_at, item.version))
    if latest.status != ArtifactStatus.FAILED.value or not latest.error_code:
        return None
    return PetErrorView(
        code=latest.error_code,
        message=latest.error_message or "建档没有完成。",
        # 旧记录没有保存此字段，只对旧数据沿用历史规则。
        retryable=latest.retryable if latest.retryable is not None else latest.error_code in LEGACY_RETRYABLE_ERROR_CODES,
    )


def _thumbnail(pet: PetProfileModel, artifacts: list[PetArtifactModel]) -> str | None:
    chosen = None
    if pet.active_character_card_id:
        chosen = next((item for item in artifacts if item.artifact_id == pet.active_character_card_id and item.path), None)
    if chosen is None:
        cards = [
            item
            for item in artifacts
            if item.kind == ArtifactKind.CHARACTER_CARD.value and item.status == ArtifactStatus.SUCCEEDED.value and item.path
        ]
        chosen = max(cards, key=lambda item: item.version) if cards else None
    if chosen is None:
        photos = [item for item in artifacts if item.kind == ArtifactKind.ID_PHOTO.value and item.path]
        chosen = photos[0] if photos else None
    if chosen is None or chosen.path is None:
        return None
    return pet_relative_path(pet.pet_id, chosen.path)


def _appearance(raw: str | None) -> PetAppearance | None:
    if not raw:
        return None
    try:
        return PetAppearance.model_validate_json(raw)
    except ValidationError:
        logger.warning("stored appearance json is invalid")
        return None


def _safe_relative(file_path: str) -> str:
    pure = PurePosixPath(file_path.replace("\\", "/").lstrip("/"))
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise AppError("PET_NOT_FOUND", "没有找到这张图片。", status_code=404)
    return pure.as_posix()
