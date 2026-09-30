from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


class ImageProcessingError(ValueError):
    """图片无法解码、格式不受支持或转换失败。"""


@dataclass(frozen=True)
class ProcessedImage:
    """解码或转换后的图片字节及对应文件扩展名。"""

    data: bytes
    extension: str


class ImageProcessor:
    """统一处理图片解码、上传预处理和输出格式转换。"""

    _FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
    _DECODE_ERRORS = (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)

    @classmethod
    def prepare_upload(cls, data: bytes) -> ProcessedImage:
        """普通格式保留原始内容，MPO 主图校正方向后转成普通 JPEG。"""
        try:
            with Image.open(BytesIO(data)) as image:
                image.load()
                if image.width < 1 or image.height < 1:
                    raise ImageProcessingError("图片尺寸无效。")
                if image.format == "MPO":
                    image.seek(0)
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    buffer = BytesIO()
                    normalized.save(buffer, format="JPEG", quality=95)
                    return ProcessedImage(buffer.getvalue(), "jpg")
                extension = cls._FORMATS.get(image.format or "")
                if extension is None:
                    raise ImageProcessingError("图片格式不受支持。")
                return ProcessedImage(data, extension)
        except cls._DECODE_ERRORS as exc:
            raise ImageProcessingError("图片无法读取或格式不受支持。") from exc

    @classmethod
    def validate_file(cls, path: Path) -> None:
        """检查已保存的标准图片，避免把未转换的 MPO 交给模型。"""
        try:
            with Image.open(path) as image:
                if image.format not in cls._FORMATS or image.width < 1 or image.height < 1:
                    raise ImageProcessingError("图片格式不受支持。")
                image.load()
        except cls._DECODE_ERRORS as exc:
            raise ImageProcessingError("图片文件丢失、无法读取或格式不受支持。") from exc

    @classmethod
    def ensure_png(cls, data: bytes) -> bytes:
        """将生成图片转换为 PNG，已有 PNG 保留原始内容。"""
        try:
            with Image.open(BytesIO(data)) as image:
                image.load()
                if image.format == "PNG":
                    return data
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"}:
                    normalized = normalized.convert("RGB")
                buffer = BytesIO()
                normalized.save(buffer, format="PNG")
                return buffer.getvalue()
        except cls._DECODE_ERRORS as exc:
            raise ImageProcessingError("图片无法转换为 PNG。") from exc
