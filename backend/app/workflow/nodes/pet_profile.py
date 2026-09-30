import logging

from app.application import pet_generation
from app.domain.errors import AppError
from app.domain.pets import MAX_ID_PHOTOS, MIN_ID_PHOTOS, ArtifactKind, PetAppearance, normalize_appearance
from app.domain.providers import ModelRole
from app.infrastructure.prompts.registry import PromptRegistry
from app.infrastructure.providers.image_provider import ImageProviderAdapter
from app.infrastructure.providers.langchain_responses import LangChainResponsesProvider
from app.infrastructure.storage.artifact_store import digest
from app.infrastructure.storage.image_inputs import assert_supported_image, ensure_png
from app.settings import get_settings
from app.workflow.state import PetGraphState

logger = logging.getLogger(__name__)


async def validate_pet_input(state: PetGraphState) -> PetGraphState:
    settings = get_settings()
    pet_id = state["pet_id"]
    input_hash = digest(b"invalid-photo")
    try:
        source = pet_generation.load_input(settings, pet_id)
        if source is None:
            return _deleted_state()
        if not MIN_ID_PHOTOS <= len(source.photo_paths) <= MAX_ID_PHOTOS:
            input_hash = digest(b"photo-count")
            raise AppError("IMAGE_COUNT_INVALID", "请上传 1 到 3 张证件照。", status_code=422)
        max_bytes = settings.max_image_size_mb * 1024 * 1024
        for path in source.photo_paths:
            if not path.is_file() or path.stat().st_size > max_bytes:
                input_hash = digest(b"missing-photo")
                raise AppError("VALIDATION_ERROR", "证件照文件丢失或无法读取，请重新建档。", status_code=422)
            assert_supported_image(path)
    except AppError as exc:
        logger.warning("validate_pet_input failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE, input_hash=input_hash, error=exc)
    except Exception:
        logger.exception("validate_pet_input crashed pet_id=%s", pet_id)
        error = AppError("INTERNAL_ERROR", "证件照校验没有完成。", status_code=500, retryable=True)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE, input_hash=digest(b"validate-crash"), error=error)
    return _clear()


async def extract_pet_appearance(state: PetGraphState) -> PetGraphState:
    if state.get("error_code"):
        return {}
    settings = get_settings()
    pet_id = state["pet_id"]
    input_hash = digest(b"appearance-error")
    try:
        prompt = PromptRegistry(settings.prompts_dir).load("pet-appearance")
        source = pet_generation.load_input(settings, pet_id)
        if source is None:
            return _deleted_state()
        photo_bytes = pet_generation.read_photos(source.photo_paths)
        input_hash = digest(*photo_bytes, prompt.content_hash.encode())
        if pet_generation.has_saved_appearance(pet_id, input_hash):
            logger.info("skip extract_pet_appearance pet_id=%s", pet_id)
            return _clear()
        binding = pet_generation.resolve_model(ModelRole.VISION)
        rendered = prompt.render({"name": source.name, "personality": source.personality})
        if settings.debug_raw_responses:
            logger.debug("pet-appearance prompt hash=%s", prompt.content_hash)
        provider = LangChainResponsesProvider(
            api_key=binding.api_key, base_url=binding.base_url, model=binding.model_id, timeout=settings.request_timeout_seconds,
        )
        result = await provider.parse(prompt=rendered, images=source.photo_paths, schema=PetAppearance)
        pet_generation.save_appearance(settings, pet_id, input_hash, normalize_appearance(result.value))
    except AppError as exc:
        logger.warning("extract_pet_appearance failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE, input_hash=input_hash, error=exc)
    except Exception:
        logger.exception("extract_pet_appearance crashed pet_id=%s", pet_id)
        error = AppError("INTERNAL_ERROR", "外观提取没有完成。", status_code=500, retryable=True)
        return _fail(pet_id, kind=ArtifactKind.APPEARANCE, input_hash=input_hash, error=error)
    return _clear()


async def generate_character_card(state: PetGraphState) -> PetGraphState:
    if state.get("error_code"):
        return {}
    settings = get_settings()
    pet_id = state["pet_id"]
    force = bool(state.get("force_character_card"))
    input_hash = digest(b"card-error")
    try:
        prompt = PromptRegistry(settings.prompts_dir).load("character-card")
        source = pet_generation.load_input(settings, pet_id)
        if source is None:
            return _deleted_state()
        if not source.appearance_json or not source.appearance_summary:
            raise AppError("APPEARANCE_REQUIRED", "外观还没有提取成功，不能生成角色卡。", status_code=409)
        photo_bytes = pet_generation.read_photos(source.photo_paths)
        input_hash = digest(*photo_bytes, source.appearance_json.encode(), prompt.content_hash.encode())
        if not force and pet_generation.has_saved_character_card(settings, pet_id, input_hash):
            logger.info("skip generate_character_card pet_id=%s", pet_id)
            return _clear()
        binding = pet_generation.resolve_model(ModelRole.IMAGE)
        rendered = prompt.render({
            "name": source.name, "personality": source.personality,
            "species": source.species, "appearance_summary": source.appearance_summary,
        })
        editor = ImageProviderAdapter(
            api_key=binding.api_key, base_url=binding.base_url, model=binding.model_id, timeout=settings.request_timeout_seconds,
        )
        image = await editor.edit(
            image_paths=source.photo_paths, prompt=rendered, size=settings.panel_size, quality=settings.image_quality,
        )
        pet_generation.save_character_card(settings, pet_id, input_hash, ensure_png(image))
    except AppError as exc:
        logger.warning("generate_character_card failed pet_id=%s code=%s", pet_id, exc.code)
        return _fail(pet_id, kind=ArtifactKind.CHARACTER_CARD, input_hash=input_hash, error=exc)
    except Exception:
        logger.exception("generate_character_card crashed pet_id=%s", pet_id)
        error = AppError("INTERNAL_ERROR", "角色卡生成没有完成。", status_code=500, retryable=True)
        return _fail(pet_id, kind=ArtifactKind.CHARACTER_CARD, input_hash=input_hash, error=error)
    return _clear()


async def finalize_pet_profile(state: PetGraphState) -> PetGraphState:
    pet_generation.finalize_profile(get_settings(), state["pet_id"])
    return {}


def _fail(pet_id: str, *, kind: ArtifactKind, input_hash: str, error: AppError) -> PetGraphState:
    pet_generation.record_failure(pet_id, kind=kind, input_hash=input_hash, error=error)
    return {"error_code": error.code, "error_message": error.message, "retryable": error.retryable}


def _clear() -> PetGraphState:
    return {"error_code": None, "error_message": None, "retryable": False}


def _deleted_state() -> PetGraphState:
    return {"error_code": "PET_DELETED", "error_message": "这只宠物已在回收区。", "retryable": False}
