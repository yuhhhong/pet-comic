import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.domain.errors import AppError

logger = logging.getLogger(__name__)

_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass(frozen=True)
class PromptTemplate:
    prompt_id: str
    purpose: str
    description: str
    variables: tuple[str, ...]
    body: str
    content_hash: str

    def render(self, values: dict[str, str]) -> str:
        used = set(_VARIABLE.findall(self.body))
        missing = sorted(name for name in used if name not in values or values[name] is None)
        if missing:
            raise AppError(
                "PROMPT_CONFIG_ERROR",
                f"提示词 {self.prompt_id} 缺少变量。",
                status_code=500,
                details={"variables": missing},
            )
        extra = sorted(name for name in values if name not in used)
        if extra:
            logger.warning("prompt %s received unused variables: %s", self.prompt_id, ", ".join(extra))
        return _VARIABLE.sub(lambda match: values[match.group(1)], self.body)


class PromptRegistry:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def load(self, prompt_id: str) -> PromptTemplate:
        markdown_path = self.directory / f"{prompt_id}.md"
        yaml_path = self.directory / f"{prompt_id}.yaml"
        if not markdown_path.is_file() or not yaml_path.is_file():
            raise AppError(
                "PROMPT_CONFIG_ERROR",
                f"找不到提示词 {prompt_id}。",
                status_code=500,
                details={"prompt_id": prompt_id},
            )
        markdown_bytes = markdown_path.read_bytes()
        yaml_bytes = yaml_path.read_bytes()
        metadata = yaml.safe_load(yaml_bytes.decode("utf-8"))
        if not isinstance(metadata, dict):
            raise _invalid(prompt_id)
        declared_id = metadata.get("prompt_id")
        variables = metadata.get("variables")
        purpose = metadata.get("purpose")
        description = metadata.get("description")
        if declared_id != prompt_id or not isinstance(purpose, str) or not isinstance(description, str):
            raise _invalid(prompt_id)
        if not isinstance(variables, list) or not all(isinstance(item, str) and item for item in variables):
            raise _invalid(prompt_id)
        body = markdown_bytes.decode("utf-8").strip()
        if not body:
            raise _invalid(prompt_id)
        used = set(_VARIABLE.findall(body))
        unknown = sorted(used - set(variables))
        if unknown:
            raise AppError(
                "PROMPT_CONFIG_ERROR",
                f"提示词 {prompt_id} 使用了未声明的变量。",
                status_code=500,
                details={"variables": unknown},
            )
        unused = sorted(set(variables) - used)
        if unused:
            logger.warning("prompt %s declares unused variables: %s", prompt_id, ", ".join(unused))
        content_hash = hashlib.sha256(markdown_bytes + b"\0" + yaml_bytes).hexdigest()
        return PromptTemplate(
            prompt_id=prompt_id,
            purpose=purpose,
            description=description,
            variables=tuple(variables),
            body=body,
            content_hash=content_hash,
        )


def _invalid(prompt_id: str) -> AppError:
    return AppError(
        "PROMPT_CONFIG_ERROR",
        f"提示词 {prompt_id} 的配置不正确。",
        status_code=500,
        details={"prompt_id": prompt_id},
    )
