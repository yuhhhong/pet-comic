import hashlib
from pathlib import Path
from uuid import uuid4


def digest(*parts: bytes) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)
    return hasher.hexdigest()


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def pet_relative_path(pet_id: str, stored_path: str | None) -> str | None:
    if not stored_path:
        return None
    prefix = f"pets/{pet_id}/"
    if not stored_path.startswith(prefix):
        return None
    relative = stored_path[len(prefix) :]
    if not relative or relative.startswith("/") or ".." in relative.split("/"):
        return None
    return relative
