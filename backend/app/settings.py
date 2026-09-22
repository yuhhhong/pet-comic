from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PET_COMIC_", env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path.home() / ".pet-comic"
    max_input_images: int = Field(default=12, ge=1)
    max_image_size_mb: int = Field(default=10, ge=1)
    max_running_tasks: int = Field(default=1, ge=1)
    max_model_requests_per_task: int = Field(default=3, ge=1)
    request_timeout_seconds: int = Field(default=180, ge=1)
    sse_heartbeat_seconds: int = Field(default=15, ge=1)
    panel_size: str = "1024x1024"
    image_quality: str = "auto"
    output_format: str = "png"
    grid_gap: int = Field(default=12, ge=0)
    log_level: str = "INFO"
    debug_raw_responses: bool = False

    @computed_field
    @property
    def task_dir(self) -> Path:
        return self.data_dir / "tasks"

    @computed_field
    @property
    def pet_dir(self) -> Path:
        return self.data_dir / "pets"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.task_dir, self.pet_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
