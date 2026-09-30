from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, utcnow


class ProviderModel(Base):
    """供应商的持久化配置；API Key 只保存在本地数据库。"""

    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(Text)
    api_key: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_model_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_model_refresh_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    bindings: Mapped[list["ModelBindingModel"]] = relationship(back_populates="provider")


class ModelBindingModel(Base):
    """业务角色到供应商模型的绑定，以 role 作为主键。"""

    __tablename__ = "model_bindings"

    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    model_id: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    provider: Mapped[ProviderModel] = relationship(back_populates="bindings")


class PetProfileModel(Base):
    """宠物档案主记录；图片和历次生成结果另存为产物。"""

    __tablename__ = "pet_profiles"

    pet_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    personality: Mapped[str] = mapped_column(Text)
    species: Mapped[str | None] = mapped_column(String(120), nullable=True)
    appearance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    appearance_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # 当前角色卡 ID；切换版本不删除旧的产物记录。
    active_character_card_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PetArtifactModel(Base):
    """建档产物或失败记录；同一宠物同一类型按 version 递增。"""

    __tablename__ = "pet_artifacts"
    __table_args__ = (UniqueConstraint("pet_id", "kind", "version", name="uq_pet_artifact_version"),)

    artifact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pet_id: Mapped[str] = mapped_column(ForeignKey("pet_profiles.pet_id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 同一输入和提示词的成功产物可被后续重试复用。
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 旧记录没有此字段的值，读取时按历史错误码规则推断。
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskModel(Base):
    """漫画任务的总体状态和本地任务目录。"""

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    active_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_dir: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskExecutionModel(Base):
    """一次任务执行的起点和配置快照，供继续或重试时追溯。"""

    __tablename__ = "task_executions"

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    start_node: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    config_snapshot_json: Mapped[str] = mapped_column(Text)
    prompt_versions_json: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskItemModel(Base):
    """执行中单个节点项目的结果，以输入哈希区分不同版本。"""

    __tablename__ = "task_items"

    execution_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_name: Mapped[str] = mapped_column(String(80), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskEventModel(Base):
    """任务执行时产生的事件记录，供进度展示和历史追溯。"""

    __tablename__ = "task_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    node_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
