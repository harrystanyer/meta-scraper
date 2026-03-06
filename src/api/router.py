"""FastAPI routes — Cloro-compatible monitor + pipeline CRUD + inspect."""
import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    InspectRequest,
    MonitorRequest,
    MonitorResponse,
    MonitorResult,
    PipelineCreate,
    Source,
    TaskStatusResponse,
)
from src.database import crud
from src.database.models import InstanceLog, ScrapeTask, TaskStatus
from src.database.session import async_session, get_session

router = APIRouter(prefix="/v1")
_manager = None


def set_manager(manager):
    global _manager
    _manager = manager


# --- Monitor endpoint (dynamic by pipeline name) ---


@router.post("/monitor/{pipeline_name}", response_model=MonitorResponse)
async def monitor(
    pipeline_name: str,
    request: MonitorRequest,
    session: AsyncSession = Depends(get_session),
):
    """Submit a prompt to any configured pipeline and return the response."""
    pipeline = await crud.get_pipeline_by_name(session, pipeline_name)
    if not pipeline:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")

    task = await crud.create_task(
        session, request.prompt, request.country, pipeline_id=pipeline.id
    )
    task_id = task.id
    await _manager.enqueue(task_id)

    # Release the request session — poll with short-lived sessions to avoid
    # holding DB connections for the entire polling duration (up to 180s).
    await session.close()

    _status = None
    _text = _markdown = _reason = None
    _sources = _raw = None

    for _ in range(1800):  # 900s max poll time for large batches
        await asyncio.sleep(0.5)
        async with async_session() as poll_session:
            result = await poll_session.execute(
                select(ScrapeTask).where(ScrapeTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return MonitorResponse(success=False, error="Task not found")
            _status = task.status
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                _text = task.response_text
                _sources = task.response_sources
                _markdown = task.response_markdown
                _raw = task.response_raw
                _reason = task.failure_reason
                break

    if _status == TaskStatus.COMPLETED:
        sources = [Source(**s) for s in (_sources or [])]
        result = MonitorResult(
            text=_text or "",
            sources=sources,
            markdown=_markdown or "",
            rawResponse=_raw or [] if request.include.rawResponse else [],
            model=pipeline_name,
        )
        return MonitorResponse(success=True, result=result)
    elif _status == TaskStatus.FAILED:
        return MonitorResponse(success=False, error=_reason)
    else:
        return MonitorResponse(success=False, error="Request timed out")


# --- Task status ---


@router.get("/async/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    task = await crud.get_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task_info = {
        "id": str(task.id),
        "status": task.status.value,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
    }
    response = None
    if task.status == TaskStatus.COMPLETED:
        sources = [Source(**s) for s in (task.response_sources or [])]
        response = MonitorResponse(
            success=True,
            result=MonitorResult(
                text=task.response_text or "",
                sources=sources,
                markdown=task.response_markdown or "",
            ),
        )
    elif task.status == TaskStatus.FAILED:
        response = MonitorResponse(success=False, error=task.failure_reason)
    return TaskStatusResponse(task=task_info, response=response)


# --- Pipeline CRUD ---


@router.get("/pipelines")
async def list_pipelines(session: AsyncSession = Depends(get_session)):
    pipelines = await crud.list_pipelines(session)
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "entry_url": p.entry_url,
            "is_active": p.is_active,
            "input_selector": p.input_selector,
            "capture_method": p.capture_method,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pipelines
    ]


@router.post("/pipelines")
async def create_pipeline(
    data: PipelineCreate,
    session: AsyncSession = Depends(get_session),
):
    pipeline = await crud.create_pipeline(
        session,
        **data.model_dump(exclude={"onboarding_steps"}),
        onboarding_steps=[s.model_dump() for s in data.onboarding_steps],
    )
    return {"id": str(pipeline.id), "name": pipeline.name}


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    pipeline = await crud.get_pipeline(session, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return {
        "id": str(pipeline.id),
        "name": pipeline.name,
        "description": pipeline.description,
        "entry_url": pipeline.entry_url,
        "use_google_search": pipeline.use_google_search,
        "google_search_term": pipeline.google_search_term,
        "onboarding_steps": pipeline.onboarding_steps,
        "input_selector": pipeline.input_selector,
        "submit_method": pipeline.submit_method,
        "submit_selector": pipeline.submit_selector,
        "capture_method": pipeline.capture_method,
        "ws_url_pattern": pipeline.ws_url_pattern,
        "ws_decode_base64": pipeline.ws_decode_base64,
        "ws_ignore_pattern": pipeline.ws_ignore_pattern,
        "ws_completion_signal": pipeline.ws_completion_signal,
        "dom_response_selector": pipeline.dom_response_selector,
        "user_agent": pipeline.user_agent,
        "is_active": pipeline.is_active,
        "created_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
        "updated_at": pipeline.updated_at.isoformat() if pipeline.updated_at else None,
    }


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: uuid.UUID,
    data: PipelineCreate,
    session: AsyncSession = Depends(get_session),
):
    pipeline = await crud.update_pipeline(
        session,
        pipeline_id,
        **data.model_dump(exclude={"onboarding_steps"}),
        onboarding_steps=[s.model_dump() for s in data.onboarding_steps],
    )
    return {"id": str(pipeline.id), "name": pipeline.name}


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    await crud.delete_pipeline(session, pipeline_id)
    return {"deleted": True}


# --- Page Inspector ---


@router.post("/inspect")
async def inspect_page(data: InspectRequest):
    """Launch a visible browser, scan a page, return detected elements."""
    from src.scraper.inspector import PageInspector

    inspector = PageInspector()
    result = await inspector.inspect(data.url, wait_seconds=data.wait_seconds)
    return {
        "url": result.url,
        "inputs": [vars(i) for i in result.inputs],
        "buttons": [vars(b) for b in result.buttons],
        "selects": [vars(s) for s in result.selects],
        "websockets": [
            {
                "url": ws.url,
                "message_count": ws.message_count,
                "sample_messages": ws.sample_messages,
            }
            for ws in result.websockets
        ],
    }


# --- Task History ---


@router.get("/tasks")
async def list_tasks(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List all tasks with optional status filter, newest first."""
    # Count total matching tasks for pagination
    count_query = select(func.count(ScrapeTask.id))
    if status:
        count_query = count_query.where(ScrapeTask.status == TaskStatus(status))
    total = await session.scalar(count_query) or 0

    query = select(ScrapeTask).order_by(ScrapeTask.created_at.desc())
    if status:
        query = query.where(ScrapeTask.status == TaskStatus(status))
    query = query.limit(limit).offset(offset)
    result = await session.execute(query)
    tasks = result.scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": str(t.id),
                "prompt": t.prompt,
                "country": t.country,
                "status": t.status.value,
                "instance_id": t.instance_id,
                "response_text": t.response_text,
                "failure_reason": t.failure_reason,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
    }


@router.delete("/tasks")
async def clear_tasks(session: AsyncSession = Depends(get_session)):
    """Delete all tasks and instance logs."""
    await session.execute(delete(ScrapeTask))
    await session.execute(delete(InstanceLog))
    await session.commit()
    return {"deleted": True}


# --- Metrics & Logs ---


@router.get("/metrics")
async def get_metrics(session: AsyncSession = Depends(get_session)):
    db_metrics = await crud.get_metrics(session)
    manager_metrics = _manager.get_metrics() if _manager else {}
    return {**db_metrics, **manager_metrics}


@router.get("/logs")
async def get_logs(
    instance_id: str | None = None,
    level: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    logs = await crud.get_logs(
        session, instance_id=instance_id, level=level, limit=limit, offset=offset
    )
    return [
        {
            "id": str(log.id),
            "instance_id": log.instance_id,
            "level": log.level,
            "message": log.message,
            "step": log.step,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
