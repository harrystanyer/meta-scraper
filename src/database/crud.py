"""CRUD operations for scrape tasks, pipelines, and instance logs."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import InstanceLog, Pipeline, ScrapeTask, TaskStatus

# --- Pipeline CRUD ---


async def create_pipeline(session: AsyncSession, **kwargs) -> Pipeline:
    pipeline = Pipeline(**kwargs)
    session.add(pipeline)
    await session.commit()
    await session.refresh(pipeline)
    return pipeline


async def get_pipeline(session: AsyncSession, pipeline_id: uuid.UUID) -> Pipeline | None:
    return await session.get(Pipeline, pipeline_id)


async def get_pipeline_by_name(session: AsyncSession, name: str) -> Pipeline | None:
    result = await session.execute(select(Pipeline).where(Pipeline.name == name))
    return result.scalar_one_or_none()


async def list_pipelines(session: AsyncSession) -> list[Pipeline]:
    result = await session.execute(select(Pipeline).order_by(Pipeline.name))
    return list(result.scalars().all())


async def update_pipeline(session: AsyncSession, pipeline_id: uuid.UUID, **kwargs) -> Pipeline:
    pipeline = await session.get(Pipeline, pipeline_id)
    for key, value in kwargs.items():
        setattr(pipeline, key, value)
    await session.commit()
    await session.refresh(pipeline)
    return pipeline


async def delete_pipeline(session: AsyncSession, pipeline_id: uuid.UUID) -> None:
    pipeline = await session.get(Pipeline, pipeline_id)
    if pipeline:
        await session.delete(pipeline)
        await session.commit()


# --- Task CRUD ---


async def create_task(
    session: AsyncSession,
    prompt: str,
    country: str = "US",
    pipeline_id: uuid.UUID | None = None,
) -> ScrapeTask:
    task = ScrapeTask(prompt=prompt, country=country, pipeline_id=pipeline_id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> ScrapeTask | None:
    return await session.get(ScrapeTask, task_id)


async def update_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: TaskStatus,
    instance_id: str | None = None,
    response_text: str | None = None,
    response_sources: dict | None = None,
    response_markdown: str | None = None,
    response_raw: dict | None = None,
    failure_reason: str | None = None,
    failure_step: str | None = None,
) -> ScrapeTask:
    task = await session.get(ScrapeTask, task_id)
    task.status = status
    if instance_id:
        task.instance_id = instance_id
    if response_text is not None:
        task.response_text = response_text
    if response_sources is not None:
        task.response_sources = response_sources
    if response_markdown is not None:
        task.response_markdown = response_markdown
    if response_raw is not None:
        task.response_raw = response_raw
    if failure_reason is not None:
        task.failure_reason = failure_reason
    if failure_step is not None:
        task.failure_step = failure_step
    if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        task.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(task)
    return task


async def get_metrics(session: AsyncSession) -> dict:
    """Get dashboard metrics."""
    total = await session.scalar(select(func.count(ScrapeTask.id)))
    completed = await session.scalar(
        select(func.count(ScrapeTask.id)).where(ScrapeTask.status == TaskStatus.COMPLETED)
    )
    failed = await session.scalar(
        select(func.count(ScrapeTask.id)).where(ScrapeTask.status == TaskStatus.FAILED)
    )
    queued = await session.scalar(
        select(func.count(ScrapeTask.id)).where(ScrapeTask.status == TaskStatus.QUEUED)
    )
    processing = await session.scalar(
        select(func.count(ScrapeTask.id)).where(ScrapeTask.status == TaskStatus.PROCESSING)
    )
    return {
        "total": total or 0,
        "completed": completed or 0,
        "failed": failed or 0,
        "queued": queued or 0,
        "processing": processing or 0,
        "success_rate": (completed / total * 100) if total else 0,
        "failure_rate": (failed / total * 100) if total else 0,
    }


# --- Log CRUD ---


async def add_log(
    session: AsyncSession,
    instance_id: str,
    message: str,
    level: str = "INFO",
    step: str | None = None,
) -> InstanceLog:
    log = InstanceLog(instance_id=instance_id, message=message, level=level, step=step)
    session.add(log)
    await session.commit()
    return log


async def get_logs(
    session: AsyncSession,
    instance_id: str | None = None,
    level: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[InstanceLog]:
    query = select(InstanceLog).order_by(InstanceLog.created_at.desc())
    if instance_id:
        query = query.where(InstanceLog.instance_id == instance_id)
    if level:
        query = query.where(InstanceLog.level == level)
    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    return list(result.scalars().all())
