from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.domain.errors import AppError


class ModelRole(str, Enum):
    """模型在业务流程中的用途；一个角色最多绑定一个模型。"""

    # 提取宠物外观并理解输入照片。
    VISION = "vision"
    # 生成漫画剧本。
    SCRIPT = "script"
    # 生成角色卡和漫画格图片。
    IMAGE = "image"


def missing_provider_error(missing_roles: list[str]) -> AppError:
    if missing_roles == [ModelRole.VISION.value]:
        message = "还没有绑定可用的视觉模型。"
    elif missing_roles == [ModelRole.IMAGE.value]:
        message = "还没有绑定可用的图像模型。"
    else:
        message = "还没有绑定可用的视觉模型和图像模型。"
    return AppError(
        "PROVIDER_NOT_CONFIGURED",
        message,
        status_code=422,
        details={"missing_roles": missing_roles},
        retryable=True,
    )


class ProviderView(BaseModel):
    """供应商的公开配置，不返回完整 API Key。"""

    id: str
    display_name: str
    base_url: str
    enabled: bool
    has_api_key: bool
    api_key_hint: str
    last_model_refresh_at: datetime | None
    last_model_refresh_error: str | None
    created_at: datetime
    updated_at: datetime


class RemoteModelList(BaseModel):
    """当前服务进程缓存的远端模型列表及最近刷新结果。"""

    provider_id: str
    models: list[str]
    refreshed_at: datetime | None
    error: str | None


class ModelBindingView(BaseModel):
    """一个业务角色当前绑定的供应商和模型。"""

    provider_id: str
    provider_name: str
    model_id: str
    provider_enabled: bool


class ModelBindingSet(BaseModel):
    """视觉、剧本、图像三个角色的完整绑定视图。"""

    vision: ModelBindingView | None
    script: ModelBindingView | None
    image: ModelBindingView | None


def mask_api_key(api_key: str) -> tuple[bool, str]:
    stripped = api_key.strip()
    if not stripped:
        return False, "未设置"
    if len(stripped) <= 4:
        return True, "已设置"
    return True, f"已设置，末四位 {stripped[-4:]}"
