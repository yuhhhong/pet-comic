from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, ValidationError

from app.api.deps import get_pet_service
from app.api.errors import public_validation_errors
from app.application.pet_profile_service import PetProfileService
from app.domain.errors import AppError
from app.domain.pets import MAX_ID_PHOTOS, PetDetail, PetProfileStatus, PetSummary

router = APIRouter(prefix="/api/pets", tags=["pets"])


class PetCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    personality: str


class PetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    personality: str | None = None
    enabled: bool | None = None


@router.get("", summary="列出宠物档案")
def list_pets(
    status: PetProfileStatus | None = None,
    trashed: bool = False,
    service: PetProfileService = Depends(get_pet_service),
) -> list[PetSummary]:
    return service.list_profiles(status=status, trashed=trashed)


@router.post("", status_code=201, summary="创建宠物档案")
async def create_pet(
    payload: Annotated[str, Form()],
    photos: Annotated[list[UploadFile] | None, File()] = None,
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
def get_pet(pet_id: str, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return service.get(pet_id)


@router.patch("/{pet_id}", summary="修改宠物档案")
async def update_pet(
    pet_id: str,
    body: PetPatch,
    service: PetProfileService = Depends(get_pet_service),
) -> PetDetail:
    return await service.update(pet_id, name=body.name, personality=body.personality, enabled=body.enabled)


@router.post("/{pet_id}/retry", summary="重试宠物建档")
async def retry_pet(pet_id: str, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return await service.retry(pet_id)


@router.post("/{pet_id}/character-card/retry", summary="重试角色卡")
async def retry_character_card(pet_id: str, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return await service.retry_character_card(pet_id)


@router.post("/{pet_id}/trash", summary="把宠物档案放入回收区")
def trash_pet(pet_id: str, service: PetProfileService = Depends(get_pet_service)) -> PetDetail:
    return service.trash(pet_id)


@router.delete("/{pet_id}", status_code=204, summary="永久删除宠物档案")
def delete_pet(pet_id: str, service: PetProfileService = Depends(get_pet_service)) -> Response:
    service.delete(pet_id)
    return Response(status_code=204)


@router.get("/{pet_id}/files/{file_path:path}", summary="读取宠物档案图片")
def get_pet_file(
    pet_id: str,
    file_path: str,
    service: PetProfileService = Depends(get_pet_service),
) -> FileResponse:
    return FileResponse(service.resolve_file(pet_id, file_path), content_disposition_type="inline")
