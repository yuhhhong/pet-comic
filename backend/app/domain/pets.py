from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.errors import AppError

MIN_ID_PHOTOS = 1
MAX_ID_PHOTOS = 3
MAX_NAME_LENGTH = 40
MAX_PERSONALITY_LENGTH = 1000

RETRYABLE_ERROR_CODES = {
    "PROVIDER_NOT_CONFIGURED",
    "MODEL_REQUEST_FAILED",
    "IMAGE_GENERATION_FAILED",
    "PROMPT_CONFIG_ERROR",
    "APPEARANCE_REQUIRED",
    "INTERNAL_ERROR",
}


class PetProfileStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    DISABLED = "disabled"


class ArtifactKind(str, Enum):
    ID_PHOTO = "id_photo"
    APPEARANCE = "appearance"
    CHARACTER_CARD = "character_card"


class ArtifactStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PetAppearance(BaseModel):
    model_config = ConfigDict(extra="ignore")

    species: str = Field(description="物种，例如猫或狗")
    breed: str = Field(description="能确认的品种；无法确认时写未知")
    coat_color: str = Field(description="主要毛色")
    coat_pattern: str = Field(description="花纹，例如纯色、虎斑、双色；无法确认时写未知")
    eye_color: str = Field(description="眼睛颜色；看不清时写未知")
    body_size: str = Field(description="体型，例如小型或中型；无法确认时写未知")
    distinctive_marks: list[str] = Field(description="稳定且能用来区分这只宠物的标记，没有则返回空数组")
    summary: str = Field(description="一句中文外观摘要，供后续匹配使用")


class PetErrorView(BaseModel):
    code: str
    message: str
    retryable: bool


class PetArtifactView(BaseModel):
    artifact_id: str
    kind: ArtifactKind
    version: int
    path: str | None
    status: ArtifactStatus
    error_code: str | None
    created_at: datetime


class PetDetail(BaseModel):
    pet_id: str
    name: str
    personality: str
    species: str | None
    appearance: PetAppearance | None
    appearance_summary: str | None
    status: PetProfileStatus
    active_character_card_id: str | None
    id_photos: list[PetArtifactView]
    character_cards: list[PetArtifactView]
    error: PetErrorView | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PetSummary(BaseModel):
    pet_id: str
    name: str
    personality: str
    species: str | None
    appearance_summary: str | None
    status: PetProfileStatus
    thumbnail_path: str | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


def normalize_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise AppError("VALIDATION_ERROR", "请填写宠物名字。", status_code=422, details={"field": "name"})
    if len(name) > MAX_NAME_LENGTH:
        raise AppError("VALIDATION_ERROR", "宠物名字不能超过 40 个字。", status_code=422, details={"field": "name"})
    return name


def normalize_personality(value: str) -> str:
    text = value.strip()
    if not text:
        raise AppError("VALIDATION_ERROR", "请填写宠物性格。", status_code=422, details={"field": "personality"})
    if len(text) > MAX_PERSONALITY_LENGTH:
        raise AppError(
            "VALIDATION_ERROR",
            "性格不能超过 1000 个字。",
            status_code=422,
            details={"field": "personality"},
        )
    return text


def normalize_appearance(appearance: PetAppearance) -> PetAppearance:
    def clean(value: str, *, limit: int, fallback: str = "未知") -> str:
        text = " ".join(value.split())
        return (text or fallback)[:limit]

    marks: list[str] = []
    for mark in appearance.distinctive_marks:
        text = " ".join(str(mark).split())
        if text and text not in marks:
            marks.append(text[:80])
        if len(marks) == 8:
            break
    return appearance.model_copy(
        update={
            "species": clean(appearance.species, limit=120),
            "breed": clean(appearance.breed, limit=120),
            "coat_color": clean(appearance.coat_color, limit=120),
            "coat_pattern": clean(appearance.coat_pattern, limit=120),
            "eye_color": clean(appearance.eye_color, limit=120),
            "body_size": clean(appearance.body_size, limit=120),
            "distinctive_marks": marks,
            "summary": clean(appearance.summary, limit=500, fallback="外观摘要未提供"),
        }
    )
