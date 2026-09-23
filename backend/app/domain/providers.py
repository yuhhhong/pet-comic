from enum import Enum

from app.domain.errors import AppError


class ModelRole(str, Enum):
    VISION = "vision"
    SCRIPT = "script"
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
