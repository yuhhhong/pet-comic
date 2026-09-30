import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.domain.errors import AppError
from app.infrastructure.providers.errors import model_call_error
from app.infrastructure.storage.image_types import image_mime_type

logger = logging.getLogger(__name__)

# 视觉理解固定走 Responses API，不回退 Chat Completions。


@dataclass(frozen=True)
class StructuredResult[T: BaseModel]:
    """结构化模型结果及调用用量，T 是解析后的 Pydantic 类型。"""

    value: T
    usage: dict[str, int]
    model: str


class LangChainResponsesProvider:
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            use_responses_api=True,
        )

    async def parse[T: BaseModel](self, *, prompt: str, images: list[Path], schema: type[T]) -> StructuredResult[T]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for path in images:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_mime_type(path)};base64,{encoded}"},
                }
            )
        try:
            result = await self._llm.with_structured_output(
                schema,
                method="json_schema",
                strict=True,
                include_raw=True,
            ).ainvoke([HumanMessage(content=content)])
        except Exception as exc:
            raise model_call_error(exc, secret=self._api_key, image=False) from exc
        parsed, raw = _unwrap(result, schema)
        usage = _usage(raw)
        logger.info(
            "vision request completed model=%s total_tokens=%s",
            self._model,
            usage["total_tokens"],
        )
        return StructuredResult(value=parsed, usage=usage, model=self._model)


def _unwrap[T: BaseModel](result: Any, schema: type[T]) -> tuple[T, Any]:
    if isinstance(result, schema):
        return result, None
    if isinstance(result, dict) and "parsed" in result:
        parsing_error = result.get("parsing_error")
        if parsing_error is not None:
            raise AppError(
                "MODEL_REQUEST_FAILED",
                "视觉模型没有返回可用的结构化外观。",
                status_code=502,
                retryable=True,
            )
        parsed = result.get("parsed")
        if isinstance(parsed, schema):
            return parsed, result.get("raw")
        if isinstance(parsed, dict):
            return schema.model_validate(parsed), result.get("raw")
    raise AppError(
        "MODEL_REQUEST_FAILED",
        "视觉模型没有返回可用的结构化外观。",
        status_code=502,
        retryable=True,
    )


def _usage(message: Any) -> dict[str, int]:
    metadata = getattr(message, "usage_metadata", None)
    if metadata is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if hasattr(metadata, "model_dump"):
        metadata = metadata.model_dump()
    elif not isinstance(metadata, dict):
        metadata = dict(metadata)
    return {
        "input_tokens": int(metadata.get("input_tokens") or 0),
        "output_tokens": int(metadata.get("output_tokens") or 0),
        "total_tokens": int(metadata.get("total_tokens") or 0),
    }
