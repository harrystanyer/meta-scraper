"""Manages a pool of config-driven ScrapeInstance objects."""
import asyncio
import uuid

from src.config import settings
from src.database import crud
from src.database.models import Pipeline, TaskStatus
from src.database.session import async_session
from src.events import Event, EventType, event_bus
from src.scraper.instance import ScrapeInstance


class ScrapeManager:
    """Coordinates browser instances across pipelines.

    Each instance gets its own serial task queue so prompts never overlap
    on the same browser tab.
    """

    def __init__(self):
        self._instances: dict[str, ScrapeInstance] = {}
        # Per-instance serial queues
        self._instance_queues: dict[str, asyncio.Queue[uuid.UUID]] = {}
        self._instance_workers: dict[str, asyncio.Task] = {}
        # Global intake queue
        self._queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._running = False
        self._dispatcher_task: asyncio.Task | None = None
        self._metrics = {
            "total_processed": 0,
            "total_failed": 0,
        }

    async def start(self, default_pipeline_name: str = "meta-ai") -> None:
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
        for task in self._instance_workers.values():
            task.cancel()
        for instance in list(self._instances.values()):
            await instance.stop()
        self._instances.clear()
        self._instance_queues.clear()
        self._instance_workers.clear()

    async def enqueue(self, task_id: uuid.UUID) -> None:
        await self._queue.put(task_id)
        await self._emit_metrics()

    # --- Instance lifecycle ---

    async def _spawn_instance(self, pipeline: Pipeline) -> ScrapeInstance:
        instance = ScrapeInstance(pipeline)
        instance._log_callback = self._log_instance_message
        try:
            await instance.start()
        except Exception as e:
            await self._log_instance_message(
                instance.id, f"Failed to start: {e}", level="ERROR", step="startup"
            )
            raise

        # Register instance + its serial queue + worker
        self._instances[instance.id] = instance
        q: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._instance_queues[instance.id] = q
        self._instance_workers[instance.id] = asyncio.create_task(
            self._instance_worker(instance, q)
        )

        await event_bus.emit(
            Event(
                type=EventType.INSTANCE_STATUS,
                data={
                    "instance_id": instance.id,
                    "pipeline": pipeline.name,
                    "status": "ready",
                },
            )
        )
        await self._emit_metrics()
        return instance

    async def _refresh_instance(self, instance: ScrapeInstance) -> None:
        """Refresh a rate-limited instance: re-navigate and re-onboard."""
        iid = instance.id
        await self._log_instance_message(iid, "Refreshing rate-limited instance", step="refresh")

        # Drain any pending tasks from this instance's queue back to global queue
        q = self._instance_queues.get(iid)
        if q:
            requeued = 0
            while not q.empty():
                try:
                    task_id = q.get_nowait()
                    await self._queue.put(task_id)
                    requeued += 1
                except asyncio.QueueEmpty:
                    break
            if requeued:
                await self._log_instance_message(
                    iid, f"Re-queued {requeued} pending tasks", step="refresh"
                )

        try:
            await instance.refresh()
            await self._log_instance_message(iid, "Instance refreshed successfully", step="refresh")
        except Exception as e:
            await self._log_instance_message(
                iid, f"Refresh failed, removing instance: {e}", level="ERROR", step="refresh"
            )
            await self._remove_instance(instance)
        await self._emit_metrics()

    async def _remove_instance(self, instance: ScrapeInstance) -> None:
        """Fully shut down and remove an instance from the pool."""
        iid = instance.id
        try:
            await instance.stop()
        except Exception:
            pass
        self._instances.pop(iid, None)
        self._instance_queues.pop(iid, None)
        worker = self._instance_workers.pop(iid, None)
        if worker:
            worker.cancel()
        await self._emit_metrics()

    # --- Dispatcher: routes tasks to instance queues ---

    async def _dispatch_loop(self) -> None:
        while self._running:
            # Refresh rate-limited instances (re-navigate + re-onboard)
            for inst in list(self._instances.values()):
                if inst.is_rate_limited:
                    await self._refresh_instance(inst)

            try:
                task_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            async with async_session() as session:
                task = await crud.get_task(session, task_id)
                if not task:
                    continue

                pipeline = (
                    await crud.get_pipeline(session, task.pipeline_id)
                    if task.pipeline_id
                    else None
                )

            # Find an idle instance or spawn a new one
            target = self._find_least_loaded_instance(pipeline)

            if not target and pipeline:
                if len(self._instances) < settings.pool_max_instances:
                    try:
                        target = await self._spawn_instance(pipeline)
                    except Exception:
                        # Re-queue and retry later
                        await self._queue.put(task_id)
                        await asyncio.sleep(3)
                        continue

            if not target:
                # All instances busy, pool full — pick the one with smallest queue
                target = self._find_least_loaded_instance(pipeline, allow_busy=True)

            if not target:
                await self._queue.put(task_id)
                await asyncio.sleep(1)
                continue

            # Route task to that instance's serial queue
            q = self._instance_queues.get(target.id)
            if q:
                await q.put(task_id)

    def _find_least_loaded_instance(
        self, pipeline: Pipeline | None, allow_busy: bool = False
    ) -> ScrapeInstance | None:
        """Find an instance for the pipeline, preferring idle ones."""
        best = None
        best_qsize = float("inf")
        for inst in self._instances.values():
            if inst.is_rate_limited:
                continue
            if pipeline and inst.pipeline.id != pipeline.id:
                continue
            if not allow_busy and inst._busy:
                continue
            q = self._instance_queues.get(inst.id)
            qsize = q.qsize() if q else 0
            if not inst._busy and qsize == 0:
                return inst  # Idle — use immediately
            if allow_busy and qsize < best_qsize:
                best = inst
                best_qsize = qsize
        return best

    # --- Per-instance worker: processes tasks one at a time ---

    async def _instance_worker(
        self, instance: ScrapeInstance, q: asyncio.Queue[uuid.UUID]
    ) -> None:
        """Serial worker — processes tasks one-by-one on a single instance."""
        while self._running and not instance.is_rate_limited:
            try:
                task_id = await asyncio.wait_for(q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            await self._process_task(instance, task_id)

    async def _process_task(self, instance: ScrapeInstance, task_id: uuid.UUID) -> None:
        async with async_session() as session:
            task = await crud.get_task(session, task_id)
            if not task:
                return

            await crud.update_task_status(
                session, task_id, TaskStatus.PROCESSING, instance_id=instance.id
            )
            await event_bus.emit(
                Event(
                    type=EventType.TASK_UPDATE,
                    data={
                        "task_id": str(task_id),
                        "status": "PROCESSING",
                        "instance_id": instance.id,
                    },
                )
            )

            try:
                result = await instance.submit_prompt(task.prompt, timeout=60.0)
                if not result.text.strip():
                    # Empty response — refresh the instance and re-queue
                    await self._log_instance_message(
                        instance.id,
                        f"Empty response for task {task_id}, refreshing instance",
                        level="WARN",
                        step="empty_response",
                    )
                    await crud.update_task_status(
                        session, task_id, TaskStatus.QUEUED
                    )
                    await self._queue.put(task_id)
                    try:
                        await instance.refresh()
                    except Exception:
                        pass
                    return
                await crud.update_task_status(
                    session,
                    task_id,
                    TaskStatus.COMPLETED,
                    response_text=result.text,
                    response_sources=result.sources,
                    response_markdown=result.markdown,
                    response_raw=list(result.raw_messages),
                )
                self._metrics["total_processed"] += 1
                await event_bus.emit(
                    Event(
                        type=EventType.TASK_UPDATE,
                        data={"task_id": str(task_id), "status": "COMPLETED"},
                    )
                )
            except Exception as e:
                if instance.is_rate_limited:
                    # Rate-limited — re-queue the task instead of marking it failed
                    await crud.update_task_status(
                        session, task_id, TaskStatus.QUEUED
                    )
                    await self._queue.put(task_id)
                    await self._log_instance_message(
                        instance.id,
                        f"Task {task_id} re-queued due to rate limit",
                        step="rate_limit",
                    )
                else:
                    await crud.update_task_status(
                        session,
                        task_id,
                        TaskStatus.FAILED,
                        failure_reason=str(e),
                        failure_step="prompt_submission",
                    )
                    self._metrics["total_failed"] += 1
                    await event_bus.emit(
                        Event(
                            type=EventType.TASK_UPDATE,
                            data={
                                "task_id": str(task_id),
                                "status": "FAILED",
                                "error": str(e),
                            },
                        )
                    )
            await self._emit_metrics()

    # --- Logging & metrics ---

    async def _log_instance_message(
        self, instance_id: str, message: str, level: str = "INFO", step: str = ""
    ) -> None:
        async with async_session() as session:
            await crud.add_log(session, instance_id, message, level=level, step=step)
        await event_bus.emit(
            Event(
                type=EventType.LOG,
                data={
                    "instance_id": instance_id,
                    "level": level,
                    "message": message,
                    "step": step,
                },
            )
        )

    async def _emit_metrics(self) -> None:
        await event_bus.emit(Event(type=EventType.METRIC_UPDATE, data=self.get_metrics()))

    def get_metrics(self) -> dict:
        return {
            **self._metrics,
            "active_instances": len(self._instances),
            "queue_size": self._queue.qsize(),
            "instance_ids": list(self._instances.keys()),
        }
