"""Generic rate-limited queue processor."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from loguru import logger

T = TypeVar("T")


class Throttle(Generic[T]):
    """Rate-limited queue that processes items via an async worker.

    Items are consumed one at a time with a configurable delay between
    each, preventing downstream rate limits from being hit.

    Usage::

        throttle = Throttle(worker=my_coroutine, rate=1.0)
        throttle.start()
        for item in items:
            await throttle.put(item)
        await throttle.join()  # wait for all items to finish
        throttle.stop()
    """

    def __init__(
        self,
        worker: Callable[[T], Awaitable[None]],
        rate: float = 1.0,
    ) -> None:
        self._worker = worker
        self._rate = rate
        self._queue: asyncio.Queue[T] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Spawn the background consumer task."""
        self._task = asyncio.create_task(self._consumer(), name="throttle_consumer")
        logger.debug(f"Throttle started (rate={self._rate}/s)")

    def stop(self) -> None:
        """Cancel the background consumer task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.debug("Throttle stopped")

    async def put(self, item: T) -> None:
        """Enqueue an item for processing."""
        await self._queue.put(item)

    async def join(self) -> None:
        """Wait until all queued items have been processed."""
        await self._queue.join()

    async def _consumer(self) -> None:
        while True:
            try:
                item = await self._queue.get()
                try:
                    await self._worker(item)
                finally:
                    self._queue.task_done()
                await asyncio.sleep(1.0 / self._rate)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Throttle consumer error: {e}")
