from pathlib import Path


_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def image_mime_type(path: Path) -> str:
    return _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
