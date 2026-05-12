from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Awaitable

from src.core.types import Event, EventType

Handler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, event: Event) -> None:
        handlers = self._handlers.get(event.type, [])
        coros = []
        for h in handlers:
            result = h(event)
            if asyncio.iscoroutine(result):
                coros.append(result)
        if coros:
            await asyncio.gather(*coros)
