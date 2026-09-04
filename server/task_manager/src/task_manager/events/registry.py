from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from threading import Lock
from typing import Any

from pyventus.core.processing.executor import ExecutorProcessingService
from pyventus.events import EventEmitter, EventLinker


class WireloftEventLinker(EventLinker):
    """Private Pyventus namespace for WireLoft domain events."""


class TrackedExecutorProcessingService(ExecutorProcessingService):
    """Executor processor whose pending emissions can be drained on shutdown/tests.

    Context variables are copied into the event executor. This is important for
    TaskOperation: a worker can emit a domain event and a task started by that
    event automatically inherits the high-level operation without putting an
    operation/request ID in the event payload or the worker signature.
    """

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        super().__init__(executor)
        self._executor = executor
        self._futures: set[Future[Any]] = set()
        self._futures_lock = Lock()

    def submit(self, callback, *args: Any, **kwargs: Any) -> None:
        context = copy_context()
        future = self._executor.submit(
            context.run,
            self._execute,
            callback,
            args,
            kwargs,
        )
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._discard_future)

    def _discard_future(self, future: Future[Any]) -> None:
        with self._futures_lock:
            self._futures.discard(future)

    def wait_for_tasks(self) -> None:
        """Wait until all emissions submitted so far have completed."""
        while True:
            with self._futures_lock:
                futures = set(self._futures)
            if not futures:
                return
            wait(futures)


_state_lock = Lock()
_executor: ThreadPoolExecutor | None = None
_processor: TrackedExecutorProcessingService | None = None
_emitter: EventEmitter | None = None


def _create_emitter() -> EventEmitter:
    global _executor, _processor, _emitter
    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wireloft-events")
    _processor = TrackedExecutorProcessingService(_executor)
    _emitter = EventEmitter(
        event_processor=_processor,
        event_linker=WireloftEventLinker,
    )
    return _emitter


def get_wireloft_event_emitter() -> EventEmitter:
    global _emitter
    with _state_lock:
        return _emitter if _emitter is not None else _create_emitter()


def wait_for_events() -> None:
    """Drain all domain events that have already been submitted."""
    with _state_lock:
        processor = _processor
    if processor is not None:
        processor.wait_for_tasks()


def shutdown_event_emitter() -> None:
    """Drain and reset the event executor so another app lifecycle can start cleanly."""
    global _executor, _processor, _emitter
    with _state_lock:
        processor = _processor
    if processor is not None:
        processor.wait_for_tasks()
        processor.shutdown(wait=True, cancel_futures=False)
    with _state_lock:
        _executor = None
        _processor = None
        _emitter = None
