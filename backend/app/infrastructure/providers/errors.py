from openai import APIConnectionError, APITimeoutError

from app.domain.errors import AppError

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_CAPABILITY_TOKENS = (
    "response_format",
    "json_schema",
    "structured output",
    "responses api",
    "does not support",
    "not supported",
)


def model_call_error(
    exc: Exception,
    *,
    secret: str,
    image: bool,
) -> AppError:
    reason = _public_reason(exc, secret)
    status = _status_code(exc)
    retryable = _is_retryable(exc, status)
    details: dict = {}
    if status is not None:
        details["status_code"] = status
    if reason:
        details["reason"] = reason
    if image:
        message = f"角色卡生成失败：{reason}" if reason else "角色卡生成失败。"
        return AppError("IMAGE_GENERATION_FAILED", message, status_code=502, details=details, retryable=retryable)
    if not retryable and _is_capability_failure(reason, status):
        return AppError(
            "MODEL_CAPABILITY_UNSUPPORTED",
            "当前模型不支持 Responses API 的结构化输出。",
            status_code=422,
            details=details,
            retryable=False,
        )
    message = f"视觉模型调用失败：{reason}" if reason else "视觉模型调用失败。"
    return AppError("MODEL_REQUEST_FAILED", message, status_code=502, details=details, retryable=retryable)


def _public_reason(exc: Exception, secret: str) -> str:
    text = " ".join(str(exc).split())
    if secret:
        text = text.replace(secret, "***")
    return text[:300]


def _status_code(exc: BaseException) -> int | None:
    for current in _chain(exc):
        status = getattr(current, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _is_retryable(exc: Exception, status: int | None) -> bool:
    if any(isinstance(current, (APITimeoutError, APIConnectionError)) for current in _chain(exc)):
        return True
    if status in _RETRYABLE_STATUS:
        return True
    if status is None:
        return True
    return False


def _is_capability_failure(reason: str, status: int | None) -> bool:
    if status not in {None, 400, 404, 422}:
        return False
    lowered = reason.lower()
    return any(token in lowered for token in _CAPABILITY_TOKENS)


def _chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__
