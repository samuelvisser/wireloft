from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
import re


_CALENDAR_CYCLE_START = date(2000, 1, 1)
_CALENDAR_CYCLE_DAYS = 146_097  # Gregorian calendar repeats every 400 years.
_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_WEEKDAY_NAMES = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_FIELD_PART_RE = re.compile(
    r"^(?P<start>[a-z0-9]+)(?:-(?P<end>[a-z0-9]+))?(?:/(?P<step>\d+))?$",
    re.IGNORECASE,
)


class CronExpressionError(ValueError):
    """A five-part cron expression cannot be analyzed safely."""


class WorkerCronExpressionError(ValueError):
    """A configured worker cron expression is invalid."""

    def __init__(
        self,
        *,
        setting_name: str,
        field_path: tuple[str, str],
        expression: str,
    ) -> None:
        self.setting_name = setting_name
        self.field_path = field_path
        self.expression = expression
        super().__init__(f"{setting_name} must use a valid five-part cron expression")


class WorkerCronIntervalError(ValueError):
    """A worker cron can execute more often than the Daily Wire slow-request delay."""

    def __init__(
        self,
        *,
        setting_name: str,
        field_path: tuple[str, str],
        minimum_seconds: float,
        required_seconds: float,
    ) -> None:
        self.setting_name = setting_name
        self.field_path = field_path
        self.minimum_seconds = minimum_seconds
        self.required_seconds = required_seconds
        super().__init__(
            f"{setting_name} runs as often as every {minimum_seconds:g} seconds, "
            f"but Daily Wire slow-request delay requires at least {required_seconds:g} seconds"
        )


@dataclass(frozen=True)
class _CronField:
    values: frozenset[int]
    last_day_of_month: bool = False


@dataclass(frozen=True)
class _ParsedCron:
    minutes: _CronField
    hours: _CronField
    days: _CronField
    months: _CronField
    weekdays: _CronField


SettingPath = tuple[str, ...]


def _setting_value(settings: object, path: SettingPath) -> object:
    value = settings
    for segment in path:
        value = getattr(value, segment)
    return value


@dataclass(frozen=True)
class WorkerCronDefinition:
    """Declarative link between one worker cron and the settings tree."""

    setting_name: str
    field_path: tuple[str, str]

    @property
    def enabled_field_path(self) -> tuple[str, str]:
        section, field = self.field_path
        return section, f"{field}_enabled"

    def resolve(self, settings: object) -> "WorkerCronSpec":
        return WorkerCronSpec(
            definition=self,
            enabled=bool(_setting_value(settings, self.enabled_field_path)),
            expression=str(_setting_value(settings, self.field_path)),
        )


@dataclass(frozen=True)
class WorkerCronSpec:
    definition: WorkerCronDefinition
    enabled: bool
    expression: str

    @property
    def setting_name(self) -> str:
        return self.definition.setting_name

    @property
    def field_path(self) -> tuple[str, str]:
        return self.definition.field_path

    @property
    def enabled_field_path(self) -> tuple[str, str]:
        return self.definition.enabled_field_path


WORKER_CRON_DEFINITIONS: tuple[WorkerCronDefinition, ...] = (
    WorkerCronDefinition(
        setting_name="Find episodes",
        field_path=("new_episode_schedule", "find_episodes_cron"),
    ),
    WorkerCronDefinition(
        setting_name="Monitor pending episodes",
        field_path=("new_episode_schedule", "monitor_pending_episode_cron"),
    ),
    WorkerCronDefinition(
        setting_name="Monitor no-usable-media episodes",
        field_path=("new_episode_schedule", "monitor_no_usable_media_episode_cron"),
    ),
    WorkerCronDefinition(
        setting_name="Verify downloads",
        field_path=("download_settings", "verify_downloads_cron"),
    ),
    WorkerCronDefinition(
        setting_name="File watcher scan",
        field_path=("file_watcher", "scan_cron"),
    ),
)


def _invalid_cron() -> CronExpressionError:
    return CronExpressionError("Enter a valid five-part cron expression")


def _parse_value(token: str, *, minimum: int, maximum: int, aliases: dict[str, int]) -> int:
    normalized = token.casefold()
    if normalized in aliases:
        return aliases[normalized]
    try:
        value = int(token)
    except ValueError as exc:
        raise _invalid_cron() from exc
    if value < minimum or value > maximum:
        raise _invalid_cron()
    return value


def _parse_field(
    expression: str,
    *,
    minimum: int,
    maximum: int,
    aliases: dict[str, int] | None = None,
    allow_last_day: bool = False,
) -> _CronField:
    aliases = aliases or {}
    values: set[int] = set()
    last_day_of_month = False

    for raw_part in expression.split(","):
        part = raw_part.strip()
        if not part:
            raise _invalid_cron()

        if allow_last_day and part.casefold() == "last":
            last_day_of_month = True
            continue

        if part.startswith("*"):
            if part == "*":
                step = 1
            elif part.startswith("*/") and part[2:].isdigit():
                step = int(part[2:])
                if step <= 0 or step > maximum - minimum:
                    raise _invalid_cron()
            else:
                raise _invalid_cron()
            values.update(range(minimum, maximum + 1, step))
            continue

        match = _FIELD_PART_RE.fullmatch(part)
        if match is None:
            raise _invalid_cron()

        start_token = match.group("start")
        end_token = match.group("end")
        step_token = match.group("step")
        start_is_alias = start_token.casefold() in aliases
        end_is_alias = end_token is not None and end_token.casefold() in aliases

        # APScheduler has separate named month/weekday range expressions. They
        # accept named singles/ranges, but not steps or mixed numeric/name ranges.
        if start_is_alias or end_is_alias:
            if not start_is_alias or (end_token is not None and not end_is_alias) or step_token is not None:
                raise _invalid_cron()

        start = _parse_value(
            start_token,
            minimum=minimum,
            maximum=maximum,
            aliases=aliases,
        )
        if end_token is not None:
            end = _parse_value(
                end_token,
                minimum=minimum,
                maximum=maximum,
                aliases=aliases,
            )
        elif step_token is not None:
            # APScheduler's numeric a/step range runs from a through the field
            # maximum. Without a step, a is just one value.
            end = maximum
        else:
            end = start

        if end < start:
            raise _invalid_cron()

        step = int(step_token) if step_token is not None else 1
        if step <= 0:
            raise _invalid_cron()
        if step_token is not None and step > end - start:
            raise _invalid_cron()

        values.update(range(start, end + 1, step))

    if not values and not last_day_of_month:
        raise _invalid_cron()

    return _CronField(frozenset(values), last_day_of_month=last_day_of_month)


@lru_cache(maxsize=256)
def _parse_cron(expression: str) -> _ParsedCron:
    fields = expression.split()
    if len(fields) != 5:
        raise _invalid_cron()

    minute, hour, day_of_month, month, day_of_week = fields
    return _ParsedCron(
        minutes=_parse_field(minute, minimum=0, maximum=59),
        hours=_parse_field(hour, minimum=0, maximum=23),
        days=_parse_field(
            day_of_month,
            minimum=1,
            maximum=31,
            allow_last_day=True,
        ),
        months=_parse_field(
            month,
            minimum=1,
            maximum=12,
            aliases=_MONTH_NAMES,
        ),
        weekdays=_parse_field(
            day_of_week,
            minimum=0,
            maximum=6,
            aliases=_WEEKDAY_NAMES,
        ),
    )


def validate_cron_expression(expression: str) -> None:
    """Validate the supported five-part APScheduler-style cron syntax."""
    _parse_cron(expression)


def _date_matches(parsed: _ParsedCron, value: date) -> bool:
    if value.month not in parsed.months.values:
        return False

    day_matches = value.day in parsed.days.values
    if parsed.days.last_day_of_month:
        day_matches = day_matches or value.day == monthrange(value.year, value.month)[1]
    if not day_matches:
        return False

    # APScheduler numbers weekdays Monday=0 through Sunday=6 and combines
    # day-of-month and day-of-week constraints with AND semantics.
    return value.weekday() in parsed.weekdays.values


def _has_matching_day(parsed: _ParsedCron) -> bool:
    current = _CALENDAR_CYCLE_START
    for _ in range(_CALENDAR_CYCLE_DAYS):
        if _date_matches(parsed, current):
            return True
        current += timedelta(days=1)
    return False


@lru_cache(maxsize=256)
def minimum_cron_interval_seconds(expression: str) -> float:
    """Return the exact minimum interval of a five-part cron expression.

    A five-part cron has minute precision and no year field. Its calendar pattern
    therefore repeats every 400 Gregorian years (146,097 days, also an exact
    number of weeks). We can analyze that finite cycle directly instead of
    simulating thousands of future APScheduler fire times.
    """
    parsed = _parse_cron(expression)

    times = sorted(
        hour * 60 + minute
        for hour in parsed.hours.values
        for minute in parsed.minutes.values
    )
    if not times:
        raise CronExpressionError("Cron expression must produce recurring worker runs")

    minimum_minutes: int | None = None
    if len(times) > 1:
        minimum_minutes = min(
            second - first
            for first, second in zip(times, times[1:])
        )

    minimum_cross_day_minutes = 24 * 60 - times[-1] + times[0]
    if minimum_minutes is not None and minimum_minutes <= minimum_cross_day_minutes:
        if not _has_matching_day(parsed):
            raise CronExpressionError("Cron expression must produce recurring worker runs")
        return float(minimum_minutes * 60)

    valid_days: list[int] = []
    current = _CALENDAR_CYCLE_START
    for offset in range(_CALENDAR_CYCLE_DAYS):
        if _date_matches(parsed, current):
            valid_days.append(offset)
        current += timedelta(days=1)

    if not valid_days:
        raise CronExpressionError("Cron expression must produce recurring worker runs")

    day_gaps = [
        second - first
        for first, second in zip(valid_days, valid_days[1:])
    ]
    day_gaps.append(_CALENDAR_CYCLE_DAYS - valid_days[-1] + valid_days[0])
    minimum_day_gap = min(day_gaps)

    cross_day_minutes = (
        minimum_day_gap * 24 * 60
        - times[-1]
        + times[0]
    )
    minimum_minutes = (
        cross_day_minutes
        if minimum_minutes is None
        else min(minimum_minutes, cross_day_minutes)
    )

    if minimum_minutes <= 0:
        raise CronExpressionError("Cron expression must produce recurring worker runs")
    return float(minimum_minutes * 60)


def validate_worker_cron_interval(
    expression: str,
    *,
    min_interval_ms: int,
    setting_name: str,
    field_path: tuple[str, str],
) -> None:
    try:
        minimum_seconds = minimum_cron_interval_seconds(expression)
    except CronExpressionError as exc:
        raise WorkerCronExpressionError(
            setting_name=setting_name,
            field_path=field_path,
            expression=expression,
        ) from exc

    required_seconds = max(0, min_interval_ms) / 1000.0
    if minimum_seconds + 1e-9 < required_seconds:
        raise WorkerCronIntervalError(
            setting_name=setting_name,
            field_path=field_path,
            minimum_seconds=minimum_seconds,
            required_seconds=required_seconds,
        )


def worker_cron_specs(settings: object) -> tuple[WorkerCronSpec, ...]:
    """Resolve all worker cron definitions from an AppSettings-like model."""
    return tuple(
        definition.resolve(settings)
        for definition in WORKER_CRON_DEFINITIONS
    )


def worker_cron_validation_errors(
    settings: object,
) -> tuple[WorkerCronExpressionError | WorkerCronIntervalError, ...]:
    """Return every active worker cron problem for a settings model."""
    min_slow_request_ms = int(
        _setting_value(settings, ("dw_timeout", "min_slow_request_ms"))
    )
    required_seconds = max(0, min_slow_request_ms) / 1000.0
    errors: list[WorkerCronExpressionError | WorkerCronIntervalError] = []

    for spec in worker_cron_specs(settings):
        if not spec.enabled:
            continue

        try:
            minimum_seconds = minimum_cron_interval_seconds(spec.expression)
        except CronExpressionError:
            errors.append(
                WorkerCronExpressionError(
                    setting_name=spec.setting_name,
                    field_path=spec.field_path,
                    expression=spec.expression,
                )
            )
            continue

        if minimum_seconds + 1e-9 < required_seconds:
            errors.append(
                WorkerCronIntervalError(
                    setting_name=spec.setting_name,
                    field_path=spec.field_path,
                    minimum_seconds=minimum_seconds,
                    required_seconds=required_seconds,
                )
            )

    return tuple(errors)
