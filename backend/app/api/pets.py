from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.deps import get_pet_service
from app.api.errors import public_validation_errors
from app.application.pet_profile_service import PetProfileService
from app.domain.errors import AppError
from app.domain.pets import MAX_ID_PHOTOS, PetDetail, PetProfileStatus, PetSummary

router = APIRouter(prefix="/api/pets", tags=["pets"])
PetId = Annotated[str, Path(description="宠物档案 ID，UUID 字符串")]


class PetCreatePayload(BaseModel):
    """创建档案时放在 multipart 表单 payload 字段中的 JSON。"""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(description="宠物名字，去除多余空格后最多 40 个字")
    personality: str = Field(description="宠物性格描述，最多 1000 个字")


class PetPatch(BaseModel):
    """档案的部分更新请求；未提供的字段保持原值。"""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, description="新的宠物名字，省略时保持原值")
    personality: str | None = Field(default=None, description="新的性格描述，省略时保持原值")
    enabled: bool | None = Field(default=None, description="是否启用档案；只能启用已有可用角色卡的档案")


@router.get("", summary="列出宠物档案")
def list_pets(
    status: Annotated[PetProfileStatus | None, Query(description="按档案状态筛选；省略时返回所选范围内的所有状态")] = None,
    trashed: Annotated[bool, Query(description="是否查询回收区；默认查询未放入回收区的档案")] = False,
    service: PetProfileService = Depends(get_pet_service),
) -> list[PetSummary]:
    return service.list_profiles(status=status, trashed=trashed)


@router.post("", status_code=201, summary="创建宠物档案")
async def create_pet(
    payload: Annotated[str, Form(description='宠物信息 JSON 字符串，包含 name（名字）和 personality（性格），例如 {"name":"小白","personality":"活泼"}')],
    photos: Annotated[list[UploadFile] | None, File(description="宠物证件照，上传 1 到 3 张 JPG、PNG 或 WebP 图片")] = None,
    service: PetProfileService = Depends(get_pet_service),
) -> PetDetail:
    try:
        data = PetCreatePayload.model_validate_json(payload)
    except ValidationError as exc:
        raise AppError(
            "VALIDATION_ERROR",
            "名字和性格没有填写完整。",
            status_code=422,
            details={"errors": public_validation_errors(exc.errors())},
        ) from exc
    uploads = photos or []
    if len(uploads) > MAX_ID_PHOTOS:
        raise AppError("IMAGE_COUNT_INVALID", "请上传 1 到 3 张证件照。", status_code=422)
    items = [(upload.filename or "photo", await upload.read()) for upload in uploads]
    return await service.create(name=data.name, personality=data.personality, photos=items)


@router.get("/{pet_id}", summary="查看宠物档案")
def get_pet(pet_id: PetId, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return service.get(pet_id)


@router.patch("/{pet_id}", summary="修改宠物档案")
async def update_pet(
    pet_id: PetId,
    body: PetPatch,
    service: PetProfileService = Depends(get_pet_service),
) -> PetDetail:
    return await service.update(pet_id, name=body.name, personality=body.personality, enabled=body.enabled)


@router.post("/{pet_id}/retry", summary="重试宠物建档")
async def retry_pet(pet_id: PetId, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return await service.retry(pet_id)


@router.post("/{pet_id}/character-card/retry", summary="重试角色卡")
async def retry_character_card(pet_id: PetId, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return await service.retry_character_card(pet_id)


@router.post("/{pet_id}/trash", summary="把宠物档案放入回收区")
def trash_pet(pet_id: PetId, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return service.trash(pet_id)


@router.delete("/{pet_id}", status_code=204, summary="永久删除宠物档案")
def delete_pet(pet_id: PetId, service: PetProfileService = Depends(get_pet_service)) -> Response:
    service.delete(pet_id)
    return Response(status_code=204)


@router.get("/{pet_id}/files/{file_path:path}", summary="读取宠物档案图片")
def get_pet_file(
    pet_id: PetId,
    file_path: Annotated[str, Path(description="档案内的图片相对路径，取自证件照或角色卡的 path 字段")],
    service: PetProfileService = Depends(get_pet_service),
) -> FileResponse:
    return FileResponse(service.resolve_file(pet_id, file_path), content_disposition_type="inline")
