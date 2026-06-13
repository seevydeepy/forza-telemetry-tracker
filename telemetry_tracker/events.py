"""In-process event bus used by API and SSE streaming."""

from __future__ import annotations

import asyncio
import copy


DEFAULT_MAX_QUEUE_SIZE = 1000


class EventBus:
    def __init__(self, max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE):
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        self._max_queue_size = max_queue_size
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: dict) -> None:
        stale: list[asyncio.Queue] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(copy.deepcopy(event))
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)
