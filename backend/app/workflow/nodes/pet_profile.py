import json
import logging
from pathlib import Path
from uuid import uuid4

from app.domain.errors import AppError
from app.domain.pets import ArtifactKind, ArtifactStatus, PetAppearance, normalize_appearance
from app.domain.providers import ModelRole, missing_provider_error
from app.infrastructure.db.app_db import db_session
from app.infrastructure.db.base import utcnow
from app.infrastructure.db.models import PetArtifactModel
from app.infrastructure.db.repositories.pets import PetRepository
from app.infrastructure.db.repositories.providers import ProviderRepository
from app.infrastructure.prompts.registry import PromptRegistry
from app.infrastructure.providers.image_provider import ImageProviderAdapter
from app.infrastructure.providers.langchain_responses import LangChainResponsesProvider
from app.infrastructure.storage.artifact_store import digest, write_atomic
from app.infrastructure.storage.image_inputs import assert_supported_image, ensure_png
from app.settings import Settings, get_settings
from app.workflow.state import PetGraphState

logger = logging.getLogger(__name__)


async def validate_pet_input(state: PetGraphState) -> dict:
    settings = get_settings()
    pet_id = state["pet_id"]
    try:
        with db_session() as session:
            repo = PetRepository(session)
            pet = repo.get(pet_id)
            if pet is None or pet.deleted_at is not None:
                return _deleted_state()
            paths = _photo_paths(settings, repo.artifacts(pet_id))
        if not 1 <= len(paths) <= 3:
            return _fail(
                pet_id,
                kind=ArtifactKind.APPEARANCE.value,
                input_hash=digest(b"photo-count"),
                error=AppError("IMAGE_COUNT_INVALID", "请上传 1 到 3 张证件照。", status_code=422),
            )
        max_bytes = settings.max_image_size_mb * 1024 * 1024
        for path in paths:
            if not path.is_file() or path.stat().st_size > max_bytes:
                return _fail(
                    pet_id,
                    kind=ArtifactKind.APPEARANCE.value,
                    input_hash=digest(b"missing-photo"),
                    error=AppError("VALIDATION_ERROR", "证件照文件丢失或无法读取，请重新建档。", status_code=422),
                )
            assert_supported_image(path)
    except AppError as exc:
        logger.warning("validate_pet_input failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE.value, input_hash=digest(b"invalid-photo"), error=exc)
    except Exception:
        logger.exception("validate_pet_input crashed pet_id=%s", pet_id)
        return _fail(
            pet_id,
            kind=ArtifactKind.APPEARANCE.value,
            input_hash=digest(b"validate-crash"),
            error=AppError("INTERNAL_ERROR", "证件照校验没有完成。", status_code=500, retryable=True),
        )
    return _clear()


async def extract_pet_appearance(state: PetGraphState) -> dict:
    if state.get("error_code"):
        return {}
    settings = get_settings()
    pet_id = state["pet_id"]
    try:
        prompt = PromptRegistry(settings.prompts_dir).load("pet-appearance")
        with db_session() as session:
            repo = PetRepository(session)
            pet = repo.get(pet_id)
            if pet is None or pet.deleted_at is not None:
                return _deleted_state()
            name = pet.name
            personality = pet.personality
            paths = _photo_paths(settings, repo.artifacts(pet_id))
        photo_bytes = _read_photos(paths)
        input_hash = digest(*photo_bytes, prompt.content_hash.encode())
        with db_session() as session:
            repo = PetRepository(session)
            pet = repo.get(pet_id)
            existing = repo.find_succeeded(pet_id, ArtifactKind.APPEARANCE.value, input_hash)
            if existing is not None and pet is not None and pet.appearance_json:
                logger.info("skip extract_pet_appearance pet_id=%s", pet_id)
                return _clear()
            binding = ProviderRepository(session).resolve(ModelRole.VISION)
        if binding is None:
            return _fail(
                pet_id,
                kind=ArtifactKind.APPEARANCE.value,
                input_hash=input_hash,
                error=missing_provider_error(["vision"]),
            )
        rendered = prompt.render({"name": name, "personality": personality})
        if settings.debug_raw_responses:
            logger.debug("pet-appearance prompt hash=%s", prompt.content_hash)
        provider = LangChainResponsesProvider(
            api_key=binding.api_key,
            base_url=binding.base_url,
            model=binding.model_id,
            timeout=settings.request_timeout_seconds,
        )
        result = await provider.parse(prompt=rendered, images=paths, schema=PetAppearance)
        appearance = normalize_appearance(result.value if isinstance(result.value, PetAppearance) else PetAppearance.model_validate(result.value))
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
    except AppError as exc:
        logger.warning("extract_pet_appearance failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE.value, input_hash=digest(b"appearance-error"), error=exc)
    except Exception:
        logger.exception("extract_pet_appearance crashed pet_id=%s", pet_id)
        return _fail(
            pet_id,
            kind=ArtifactKind.APPEARANCE.value,
            input_hash=digest(b"appearance-crash"),
            error=AppError("INTERNAL_ERROR", "外观提取没有完成。", status_code=500, retryable=True),
        )
    return _clear()


async def generate_character_card(state: PetGraphState) -> dict:
    if state.get("error_code"):
        return {}
    settings = get_settings()
    pet_id = state["pet_id"]
    force = bool(state.get("force_character_card"))
    try:
        prompt = PromptRegistry(settings.prompts_dir).load("character-card")
        with db_session() as session:
            repo = PetRepository(session)
            pet = repo.get(pet_id)
            if pet is None or pet.deleted_at is not None:
                return _deleted_state()
            if not pet.appearance_json or not pet.appearance_summary:
                raise AppError("APPEARANCE_REQUIRED", "外观还没有提取成功，不能生成角色卡。", status_code=409)
            name = pet.name
            personality = pet.personality
            species = pet.species or "未知"
            summary = pet.appearance_summary
            appearance_json = pet.appearance_json
            paths = _photo_paths(settings, repo.artifacts(pet_id))
        photo_bytes = _read_photos(paths)
        input_hash = digest(*photo_bytes, appearance_json.encode(), prompt.content_hash.encode())
        if not force:
            with db_session() as session:
                existing = PetRepository(session).find_succeeded(pet_id, ArtifactKind.CHARACTER_CARD.value, input_hash)
                if existing is not None and existing.path and (settings.data_dir / existing.path).is_file():
                    logger.info("skip generate_character_card pet_id=%s", pet_id)
                    return _clear()
        with db_session() as session:
            binding = ProviderRepository(session).resolve(ModelRole.IMAGE)
        if binding is None:
            return _fail(
                pet_id,
                kind=ArtifactKind.CHARACTER_CARD.value,
                input_hash=input_hash,
                error=missing_provider_error(["image"]),
            )
        rendered = prompt.render(
            {
                "name": name,
                "personality": personality,
                "species": species,
                "appearance_summary": summary,
            }
        )
        editor = ImageProviderAdapter(
            api_key=binding.api_key,
            base_url=binding.base_url,
            model=binding.model_id,
            timeout=settings.request_timeout_seconds,
        )
        png = ensure_png(
            await editor.edit(
                image_paths=paths,
                prompt=rendered,
                size=settings.panel_size,
                quality=settings.image_quality,
            )
        )
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
    except AppError as exc:
        logger.warning("generate_character_card failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.CHARACTER_CARD.value, input_hash=digest(b"card-error"), error=exc)
    except Exception:
        logger.exception("generate_character_card crashed pet_id=%s", pet_id)
        return _fail(
            pet_id,
            kind=ArtifactKind.CHARACTER_CARD.value,
            input_hash=digest(b"card-crash"),
            error=AppError("INTERNAL_ERROR", "角色卡生成没有完成。", status_code=500, retryable=True),
        )
    return _clear()


async def finalize_pet_profile(state: PetGraphState) -> dict:
    settings = get_settings()
    pet_id = state["pet_id"]
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        if pet is None or pet.deleted_at is not None:
            return {}
        card = _usable_character_card(settings, repo.artifacts(pet_id))
        if card is not None:
            pet.active_character_card_id = card.artifact_id
            if pet.status != "disabled":
                pet.status = "ready"
        elif pet.status != "disabled":
            pet.status = "draft"
            pet.active_character_card_id = None
        pet.updated_at = utcnow()
    return {}


def _photo_paths(settings: Settings, artifacts: list[PetArtifactModel]) -> list[Path]:
    photos = [
        item
        for item in artifacts
        if item.kind == ArtifactKind.ID_PHOTO.value and item.status == ArtifactStatus.SUCCEEDED.value and item.path
    ]
    photos.sort(key=lambda item: item.version)
    return [settings.data_dir / item.path for item in photos if item.path is not None]


def _usable_character_card(settings: Settings, artifacts: list[PetArtifactModel]) -> PetArtifactModel | None:
    cards = [
        item
        for item in artifacts
        if item.kind == ArtifactKind.CHARACTER_CARD.value
        and item.status == ArtifactStatus.SUCCEEDED.value
        and item.path
        and (settings.data_dir / item.path).is_file()
    ]
    if not cards:
        return None
    return max(cards, key=lambda item: item.version)


def _read_photos(paths: list[Path]) -> list[bytes]:
    try:
        return [path.read_bytes() for path in paths]
    except OSError as exc:
        raise AppError("VALIDATION_ERROR", "证件照文件丢失或无法读取，请重新建档。", status_code=422) from exc


def _fail(pet_id: str, *, kind: str, input_hash: str, error: AppError) -> dict:
    with db_session() as session:
        repo = PetRepository(session)
        pet = repo.get(pet_id)
        if pet is None:
            return _error_state(error)
        repo.add_artifact(
            pet_id=pet_id,
            kind=kind,
            version=repo.next_version(pet_id, kind),
            path=None,
            input_hash=input_hash,
            status=ArtifactStatus.FAILED.value,
            error_code=error.code,
            error_message=error.message,
            artifact_id=str(uuid4()),
        )
        pet.updated_at = utcnow()
    return _error_state(error)


def _error_state(error: AppError) -> dict:
    return {"error_code": error.code, "error_message": error.message, "retryable": error.retryable}


def _clear() -> dict:
    return {"error_code": None, "error_message": None, "retryable": False}


def _deleted_state() -> dict:
    return {"error_code": "PET_DELETED", "error_message": "这只宠物已在回收区。", "retryable": False}
