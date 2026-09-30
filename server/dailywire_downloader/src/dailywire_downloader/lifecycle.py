"""Thread-safe execution facts, independent of UI percentages and persistence."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from threading import Event, RLock, Thread
from time import monotonic, time
from typing import Callable, Iterator, Literal
from uuid import uuid4

from .errors import DownloadCancelled
from .models import DownloadProgress
from .plan import DownloadPlan, Phase, StageSpec
from .transfer_context import TransferWait, transfer_context

ActivityState = Literal["pending", "running", "waiting", "completed", "skipped", "failed", "canceled"]


@dataclass(frozen=True)
class WaitInterval:
    reason: str
    started_at: float
    finished_at: float | None = None
    until: float | None = None


@dataclass(frozen=True)
class StageSnapshot:
    id: str
    code: str
    phase: Phase
    resource: str
    weight: float
    asset_id: str | None = None
    state: ActivityState = "pending"
    started_at: float | None = None
    finished_at: float | None = None
    fraction: float | None = None
    bytes_received: int = 0
    total_bytes: int | None = None
    segments_done: int | None = None
    segments_total: int | None = None
    wait: WaitInterval | None = None
    waits: tuple[WaitInterval, ...] = ()
    last_activity_at: float | None = None
    deadline_at: float | None = None


@dataclass(frozen=True)
class StepTiming:
    code: str
    started_at: float
    finished_at: float


@dataclass(frozen=True)
class DownloadSnapshot:
    attempt_id: str
    sequence: int
    phase: Phase
    main_activity: str
    stages: tuple[StageSnapshot, ...]
    started_at: float
    heartbeat_at: float
    last_activity_at: float
    primary_transfer_complete: bool
    canceling: bool
    preparation_steps: tuple[StepTiming, ...]
    warnings: tuple[str, ...]


def download_completion_fraction(snapshot: DownloadSnapshot) -> float:
    """Return estimated whole-attempt work completion for orchestration.

    This is deliberately separate from the user-facing media-transfer
    percentage. Stage weights describe units of work, not elapsed-time
    prediction, and terminal boundaries are the only source of completion for
    unmeasurable stages.
    """
    total = 0.0
    done = 0.0
    for stage in snapshot.stages:
        weight = max(0.0, float(stage.weight))
        total += weight
        if stage.state in ("completed", "skipped"):
            fraction = 1.0
        elif stage.state in ("running", "waiting") and stage.fraction is not None:
            fraction = max(0.0, min(1.0, float(stage.fraction)))
        else:
            fraction = 0.0
        done += weight * fraction
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, done / total))


class DownloadTracker:
    """Report a coalesced snapshot; concurrent assets never replace the main activity.

    Heartbeats establish liveness, not work completion. Numerical progress only
    changes from real transfer/copy measurements or completed stage boundaries.
    """
    def __init__(
        self, sink: Callable[[DownloadSnapshot], None] | None = None,
        should_cancel: Callable[[], bool] | None = None, *, attempt_id: str | None = None,
        report_interval: float = 0.5,
    ):
        self.attempt_id = attempt_id or str(uuid4())
        self._sink = sink
        self._should_cancel = should_cancel
        self._lock = RLock()
        self._emit_lock = RLock()
        self._cancel_lock = RLock()
        self._stop = Event()
        self._cancel = Event()
        self._heartbeat: Thread | None = None
        self._report_interval = report_interval
        self._last_emit = 0.0
        self._last_cancel_check = 0.0
        self._error: BaseException | None = None
        self._started = time()
        self._activity_at = self._started
        self._sequence = 0
        self._plan: DownloadPlan | None = None
        self._phase: Phase = "preparing"
        self._main = "prepare"
        self._media_complete = False
        self._canceling = False
        self._warnings: list[str] = []
        self._preparation_steps: list[StepTiming] = []
        self._step_start = self._started
        self._step_code = "prepare"
        self._stages = {"prepare": StageSnapshot(
            "prepare", "prepare", "preparing", "none", 0.02,
            state="running", started_at=self._started, last_activity_at=self._started,
        )}

    def __enter__(self) -> DownloadTracker:
        self.emit(force=True)
        self._heartbeat = Thread(target=self._heartbeats, name="download-liveness", daemon=True)
        self._heartbeat.start()
        return self

    def stop_reporting(self) -> None:
        self._stop.set()
        if self._heartbeat is not None:
            self._heartbeat.join()
            self._heartbeat = None

    def __exit__(self, *_exc) -> None:
        self.stop_reporting()

    def _heartbeats(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self.ensure_active()
                self.emit(force=True)
            except BaseException as exc:
                self._error = exc
                self._cancel.set()
                return

    def is_canceled(self) -> bool:
        if self._cancel.is_set():
            return True
        with self._cancel_lock:
            now = monotonic()
            if self._should_cancel is not None and now - self._last_cancel_check >= 0.2:
                self._last_cancel_check = now
                if self._should_cancel():
                    self._cancel.set()
        return self._cancel.is_set()

    def ensure_active(self) -> None:
        if self._error is not None:
            raise self._error
        if self.is_canceled():
            raise DownloadCancelled("Download was canceled")

    def cancel(self, *, user_requested: bool = True) -> None:
        """Stop owned writers before cleanup; failures are not user cancellation."""
        self._cancel.set()
        with self._lock:
            self._canceling = user_requested

    @property
    def failure(self) -> BaseException | None:
        return self._error

    def fail(self, error: BaseException) -> None:
        """Abort owned parallel work when a required dependency fails."""
        with self._lock:
            if self._error is None and not self._cancel.is_set():
                self._error = error
                self._cancel.set()

    def finish(self) -> DownloadSnapshot:
        """Finish reporting before the application commits a successful result.

        No cancellable checkpoint is allowed after the database commit. The
        executor performs the terminal transition; this snapshot is its history.
        """
        self.ensure_active()
        self.stop_reporting()
        self._finish("finalize", "completed")
        with self._lock:
            self._phase = "complete"
        return self.snapshot()

    def preparing(self, code: str) -> None:
        now = time()
        with self._lock:
            self._preparation_steps.append(StepTiming(self._step_code, self._step_start, now))
            self._step_code, self._step_start = code, now
            self._stages["prepare"] = replace(self._stages["prepare"], code=code, last_activity_at=now)
            self._activity_at = now
        self.emit(force=True)

    def install(self, plan: DownloadPlan) -> None:
        if plan.attempt_id != self.attempt_id:
            raise ValueError("A plan cannot belong to a different attempt")
        with self._lock:
            if self._plan is not None:
                raise ValueError("A download attempt can only install one immutable plan")
            self._plan = plan
            prepare = self._stages["prepare"]
            self._stages = {stage.id: StageSnapshot(
                stage.id, stage.code, stage.phase, stage.resource, stage.weight, stage.asset_id,
            ) for stage in plan.stages}
            self._stages["prepare"] = prepare
            self._preparation_steps.append(StepTiming(self._step_code, self._step_start, time()))
        self.complete("prepare")

    def start(self, activity: str, *, foreground: bool = True) -> None:
        self.ensure_active()
        now = time()
        with self._lock:
            if self._plan is None:
                raise ValueError("Download stages require an installed plan")
            spec = self._plan.stage(activity)
            unfinished = [dependency for dependency in spec.depends_on
                          if self._stages[dependency].state not in ("completed", "skipped")]
            if unfinished:
                raise ValueError(f"Stage '{activity}' has unfinished dependencies: {', '.join(unfinished)}")
            deadline_seconds = spec.deadline_seconds
            stage = self._stages[activity]
            if stage.state != "pending":
                raise ValueError(f"Stage '{activity}' has already started")
            self._stages[activity] = replace(
                stage, state="running", started_at=stage.started_at or now,
                last_activity_at=now,
                deadline_at=now + deadline_seconds if deadline_seconds else None,
            )
            if foreground:
                self._main = activity
                self._phase = "finishing" if self._media_complete else stage.phase
            self._activity_at = now
        self.emit(force=True)

    def focus(self, activity: str) -> None:
        with self._lock:
            self._main = activity
            self._phase = "finishing" if self._media_complete else "transferring"
        self.emit(force=True)

    def _finish(self, activity: str, state: ActivityState) -> None:
        now = time()
        with self._lock:
            stage = self._stages[activity]
            waits = stage.waits
            if stage.wait is not None:
                waits += (replace(stage.wait, finished_at=now),)
            self._stages[activity] = replace(
                stage, state=state, fraction=1.0 if state in ("completed", "skipped") else stage.fraction,
                finished_at=now, last_activity_at=now, wait=None, waits=waits,
            )
            if activity == "media" and state == "completed":
                self._media_complete = True
                self._phase = "finishing"
            self._activity_at = now
        self.emit(force=True)

    def complete(self, activity: str) -> None:
        self._finish(activity, "completed")

    def skip(self, activity: str, warning: str) -> None:
        with self._lock:
            self._warnings.append(warning)
        self._finish(activity, "skipped")

    def wait(self, activity: str, reason: str | None, until: float | None = None) -> None:
        now = time()
        with self._lock:
            stage = self._stages[activity]
            if stage.state in ("completed", "skipped", "failed", "canceled"):
                return
            previous = stage.wait
            if (previous.reason if previous else None) == reason and (previous.until if previous else None) == until:
                return
            waits = stage.waits
            if previous is not None:
                waits += (replace(previous, finished_at=now),)
            current = WaitInterval(reason, now, until=until) if reason else None
            self._stages[activity] = replace(
                stage, wait=current, waits=waits, state="waiting" if current else "running",
                last_activity_at=now,
                deadline_at=(stage.deadline_at + now - previous.started_at) if previous and stage.deadline_at else stage.deadline_at,
            )
            self._activity_at = now
        self.emit(force=True)

    def progress(self, activity: str, progress: DownloadProgress) -> None:
        now = time()
        with self._lock:
            stage = self._stages[activity]
            moved = progress.bytes_downloaded != stage.bytes_received or progress.segments_done != stage.segments_done
            self._stages[activity] = replace(
                stage, fraction=progress.fraction, bytes_received=progress.bytes_downloaded,
                total_bytes=progress.total_bytes, segments_done=progress.segments_done,
                segments_total=progress.segments_total,
                last_activity_at=now if moved else stage.last_activity_at,
            )
            if moved:
                self._activity_at = now
        self.emit()

    def snapshot(self) -> DownloadSnapshot:
        with self._lock:
            return DownloadSnapshot(
                self.attempt_id, self._sequence, self._phase, self._main, tuple(self._stages.values()),
                self._started, time(), self._activity_at, self._media_complete, self._canceling,
                tuple(self._preparation_steps), tuple(self._warnings),
            )

    def emit(self, *, force: bool = False) -> None:
        if self._stop.is_set():
            return
        # Serialize callbacks, not I/O or state mutation. An older snapshot can
        # never overtake a newer one when an auxiliary thread reports progress.
        with self._emit_lock:
            now = monotonic()
            if not force and now - self._last_emit < self._report_interval:
                return
            self._last_emit = now
            with self._lock:
                self._sequence += 1
            if self._sink is not None:
                self._sink(self.snapshot())

    @contextmanager
    def activity(self, activity: str, *, foreground: bool = True) -> Iterator[None]:
        self.start(activity, foreground=foreground)
        def waiting(event: TransferWait | None) -> None:
            self.wait(activity, event.reason if event else None, event.until if event else None)
        try:
            with transfer_context(self.is_canceled, waiting):
                yield
            self.ensure_active()
        except BaseException as exc:
            self._finish(activity, "canceled" if isinstance(exc, DownloadCancelled) else "failed")
            raise
        else:
            self.complete(activity)
