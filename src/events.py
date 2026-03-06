"""In-process event bus for real-time UI updates."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class EventType(Enum):
    LOG = "log"
    METRIC_UPDATE = "metric_update"
    INSTANCE_STATUS = "instance_status"
    TASK_UPDATE = "task_update"


@dataclass
class Event:
    type: EventType
    data: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Simple async pub/sub. Subscribers receive events via async callbacks."""

    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = {}

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: EventType, callback: Callable) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    async def emit(self, event: Event) -> None:
        for callback in self._subscribers.get(event.type, []):
            try:
                await callback(event)
            except Exception:
                pass  # Don't let a bad subscriber break the pipeline


# Singleton instance — shared between manager and UI
event_bus = EventBus()
