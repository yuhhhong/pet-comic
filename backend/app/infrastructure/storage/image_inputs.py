from dataclasses import dataclass
from pathlib import Path

from app.domain.errors import AppError
from app.domain.pets import MAX_ID_PHOTOS, MIN_ID_PHOTOS
from app.infrastructure.storage.artifact_store import digest, write_atomic
from app.infrastructure.storage.image_processor import ImageProcessingError, ImageProcessor
from app.settings import Settings


@dataclass(frozen=True)
class ValidatedImage:
    """通过格式和大小校验、准备写入本地的证件照。"""

    filename: str
    data: bytes
    extension: str


@dataclass(frozen=True)
class StoredPhoto:
    """已保存证件照的相对路径和内容哈希。"""

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
        try:
            processed = ImageProcessor.prepare_upload(data)
        except ImageProcessingError as exc:
            raise AppError(
                "IMAGE_TYPE_UNSUPPORTED",
                f"无法读取证件照“{label}”，请换一张 JPG/JPEG、PNG 或 WebP（支持 MPO 照片自动转换）。",
                status_code=422,
                details={"filename": label},
            ) from exc
        if len(processed.data) > max_bytes:
            raise AppError(
                "IMAGE_TOO_LARGE",
                f"证件照“{label}”转换后超过 {max_image_size_mb} MB，请缩小图片后重试。",
                status_code=422,
                details={"filename": label},
            )
        validated.append(ValidatedImage(label, processed.data, processed.extension))
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
        ImageProcessor.validate_file(path)
    except ImageProcessingError as exc:
        raise AppError("VALIDATION_ERROR", "证件照文件丢失、格式不受支持或无法读取，请重新建档。", status_code=422) from exc


def ensure_png(data: bytes) -> bytes:
    try:
        return ImageProcessor.ensure_png(data)
    except ImageProcessingError as exc:
        raise AppError("IMAGE_GENERATION_FAILED", "生成的角色卡不是有效图片。", status_code=502, retryable=True) from exc


def _safe_filename(filename: str) -> str:
    label = Path(filename or "").name.strip() or "photo"
    cleaned = "".join(character for character in label if character.isprintable())
    return cleaned[:80] or "photo"
