from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.domain.errors import AppError
from app.domain.pets import MAX_ID_PHOTOS, MIN_ID_PHOTOS
from app.infrastructure.storage.artifact_store import digest, write_atomic
from app.settings import Settings

_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


@dataclass(frozen=True)
class ValidatedImage:
    filename: str
    data: bytes
    extension: str


@dataclass(frozen=True)
class StoredPhoto:
    path: str
    input_hash: str


def validate_id_photos(photos: list[tuple[str, bytes]], max_image_size_mb: int) -> list[ValidatedImage]:
    if not MIN_ID_PHOTOS <= len(photos) <= MAX_ID_PHOTOS:
        raise AppError("IMAGE_COUNT_INVALID", "请上传 1 到 3 张证件照。", status_code=422)
    max_bytes = max_image_size_mb * 1024 * 1024
    validated: list[ValidatedImage] = []
    for filename, data in photos:
        label = _safe_filename(filename)
        if not data:
            raise AppError(
                "IMAGE_TYPE_UNSUPPORTED",
                f"证件照“{label}”是空文件。",
                status_code=422,
                details={"filename": label},
            )
        if len(data) > max_bytes:
            raise AppError(
                "IMAGE_TOO_LARGE",
                f"证件照“{label}”超过 {max_image_size_mb} MB。",
                status_code=422,
                details={"filename": label},
            )
        validated.append(ValidatedImage(label, data, _sniff_image(data, label)))
    return validated


def save_id_photos(settings: Settings, pet_id: str, images: list[ValidatedImage]) -> list[StoredPhoto]:
    stored: list[StoredPhoto] = []
    for index, image in enumerate(images, start=1):
        relative = f"pets/{pet_id}/source/{index:02d}.{image.extension}"
        write_atomic(settings.data_dir / relative, image.data)
        stored.append(StoredPhoto(path=relative, input_hash=digest(image.data)))
    return stored


def assert_supported_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            if image.format not in _FORMATS or image.width < 1 or image.height < 1:
                raise AppError("IMAGE_TYPE_UNSUPPORTED", "证件照不是 JPG、PNG 或 WebP。", status_code=422)
            image.load()
    except AppError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("VALIDATION_ERROR", "证件照文件丢失或无法读取，请重新建档。", status_code=422) from exc


def ensure_png(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if image.format == "PNG" and data.startswith(b"\x89PNG"):
                return data
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("IMAGE_GENERATION_FAILED", "生成的角色卡不是有效图片。", status_code=502, retryable=True) from exc


def _sniff_image(data: bytes, label: str) -> str:
    message = f"无法读取证件照“{label}”，请换一张 JPG、PNG 或 WebP。"
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError("IMAGE_TYPE_UNSUPPORTED", message, status_code=422, details={"filename": label}) from exc
    extension = _FORMATS.get(image_format or "")
    if extension is None or width < 1 or height < 1:
        raise AppError("IMAGE_TYPE_UNSUPPORTED", message, status_code=422, details={"filename": label})
    return extension


def _safe_filename(filename: str) -> str:
    label = Path(filename or "").name.strip() or "photo"
    cleaned = "".join(character for character in label if character.isprintable())
    return cleaned[:80] or "photo"
