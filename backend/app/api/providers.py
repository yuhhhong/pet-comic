from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_provider_service
from app.application.provider_service import ProviderService
from app.domain.providers import ModelBindingSet, ProviderView, RemoteModelList

router = APIRouter(prefix="/api", tags=["providers"])
ProviderId = Annotated[str, Path(description="模型供应商 ID，UUID 字符串")]


class ProviderCreate(BaseModel):
    """创建供应商所需的本地配置。"""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(description="供应商显示名称，最多 60 个字")
    base_url: str = Field(description="HTTP(S) API 地址，通常以 /v1 结尾")
    api_key: str = Field(description="访问该供应商的 API Key，仅保存在本机数据库")
    enabled: bool = Field(default=True, description="创建后是否启用供应商")


class ProviderPatch(BaseModel):
    """供应商的部分更新请求；未提供的字段保持原值。"""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, description="新的显示名称，省略时保持原值")
    base_url: str | None = Field(default=None, description="新的 HTTP(S) API 地址，省略时保持原值")
    api_key: str | None = Field(default=None, description="新的 API Key，省略时保持原值")
    enabled: bool | None = Field(default=None, description="是否启用供应商，省略时保持原值")


class BindingInput(BaseModel):
    """单个业务角色绑定的供应商及其模型 ID。"""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(description="已启用的模型供应商 ID")
    model_id: str = Field(min_length=1, max_length=200, description="供应商模型列表中的模型 ID")


class BindingUpdate(BaseModel):
    """一次提交三个角色的绑定；null 表示解绑该角色。"""

    model_config = ConfigDict(extra="forbid")

    vision: BindingInput | None = Field(description="视觉理解模型绑定；传 null 解绑")
    script: BindingInput | None = Field(description="剧本生成模型绑定；传 null 解绑")
    image: BindingInput | None = Field(description="图像生成模型绑定；传 null 解绑")


@router.get("/providers", summary="列出模型供应商")
def list_providers(service: ProviderService = Depends(get_provider_service)) -> list[ProviderView]:
    return service.list_providers()


@router.post("/providers", status_code=201, summary="新增模型供应商")
async def create_provider(body: ProviderCreate, service: ProviderService = Depends(get_provider_service)) -> ProviderView:
    return await service.create(
        display_name=body.display_name,
        base_url=body.base_url,
        api_key=body.api_key,
        enabled=body.enabled,
    )


@router.patch("/providers/{provider_id}", summary="修改模型供应商")
async def update_provider(
    provider_id: ProviderId,
    body: ProviderPatch,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderView:
    return await service.update(
        provider_id,
        display_name=body.display_name,
        base_url=body.base_url,
        api_key=body.api_key,
        enabled=body.enabled,
    )


@router.post("/providers/{provider_id}/refresh-models", summary="刷新供应商模型列表")
async def refresh_provider_models(
    provider_id: ProviderId,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderView:
    return await service.refresh(provider_id)


@router.get("/providers/{provider_id}/models", summary="查看供应商模型列表")
def list_provider_models(provider_id: ProviderId, service: ProviderService = Depends(get_provider_service)) -> RemoteModelList:
    return service.list_models(provider_id)


@router.get("/model-bindings", summary="查看模型绑定")
def get_model_bindings(service: ProviderService = Depends(get_provider_service)) -> ModelBindingSet:
    return service.get_bindings()


@router.put("/model-bindings", summary="保存模型绑定")
def update_model_bindings(body: BindingUpdate, service: ProviderService = Depends(get_provider_service)) -> ModelBindingSet:
    return service.update_bindings(
        vision=_pair(body.vision),
        script=_pair(body.script),
        image=_pair(body.image),
    )


def _pair(value: BindingInput | None) -> tuple[str, str] | None:
    if value is None:
        return None
    return value.provider_id, value.model_id
