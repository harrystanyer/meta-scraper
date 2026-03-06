import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(5), default="US")
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.QUEUED)
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    instance_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Response data (Cloro-compatible)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Failure tracking
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_step: Mapped[str | None] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)

    # Navigation
    entry_url: Mapped[str] = mapped_column(Text, nullable=False)
    use_google_search: Mapped[bool] = mapped_column(default=False)
    google_search_term: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Onboarding steps — JSON array of step objects
    onboarding_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Prompt input
    input_selector: Mapped[str] = mapped_column(Text, nullable=False)
    submit_method: Mapped[str] = mapped_column(String(20), default="enter_key")
    submit_selector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Response capture
    capture_method: Mapped[str] = mapped_column(String(20), default="websocket")
    ws_url_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    ws_decode_base64: Mapped[bool] = mapped_column(default=False)
    ws_ignore_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    ws_completion_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    dom_response_selector: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User agent override
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InstanceLog(Base):
    __tablename__ = "instance_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(10), default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
