from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import get_settings

logger = logging.getLogger(__name__)

_TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}
_SHORTLIST_SIZE = 5
_MIN_TITLE_SIMILARITY = 0.82
_MIN_MATCH_CONFIDENCE = 0.82
_AMBIGUITY_MARGIN = 0.04
_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
})


class TMDbAPIError(RuntimeError):
    """Raised when TMDB cannot complete a metadata request."""


@dataclass(frozen=True)
class TMDbMovieMatch:
    tmdb_id: int
    title: str
    release_date: date
    confidence: float


@dataclass(frozen=True)
class TMDbLookupResult:
    status: str
    match: Optional[TMDbMovieMatch] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class MovieReleaseLookupResult:
    """Persistable result of one movie release-date lookup attempt."""

    status: str
    attempted_at: datetime
    release_date: Optional[date] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class _ScoredCandidate:
    tmdb_id: int
    title: str
    release_date: date
    confidence: float
    title_similarity: float
    popularity: float


class TMDbClient:
    """Small, dependency-free TMDB client used for one-time movie matching."""

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = "https://api.themoviedb.org/3",
        language: str = "en-US",
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        user_agent: str = "WireLoft",
    ) -> None:
        token = access_token.strip()
        if not token:
            raise ValueError("A TMDB API Read Access Token is required")
        self._access_token = token
        self._base_url = base_url.rstrip("/")
        self._language = language
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._user_agent = user_agent

    def lookup_movie(
        self,
        *,
        title: str,
        description: Optional[str] = None,
        duration_seconds: float = 0,
    ) -> TMDbLookupResult:
        requested_title = title.strip()
        if not requested_title:
            return TMDbLookupResult(
                status="not_found",
                detail="The movie has no title to search for",
            )

        search_payload = self._get_json(
            "/search/movie",
            {
                "query": requested_title,
                "include_adult": "false",
                "language": self._language,
                "page": 1,
            },
        )
        raw_results = search_payload.get("results")
        if not isinstance(raw_results, list) or not raw_results:
            return TMDbLookupResult(
                status="not_found",
                detail="TMDB returned no movie results",
            )

        requested_normalized = _normalize_title(requested_title)
        preliminaries: list[tuple[float, float, Mapping[str, Any]]] = []
        for raw in raw_results[:20]:
            if not isinstance(raw, Mapping):
                continue
            tmdb_id = raw.get("id")
            if not isinstance(tmdb_id, int):
                continue
            title_similarity = _candidate_title_similarity(requested_normalized, raw)
            if title_similarity < 0.55:
                continue
            overview_similarity = _text_similarity(description, raw.get("overview"))
            popularity = _as_float(raw.get("popularity"))
            preliminary_score = (title_similarity * 0.9) + ((overview_similarity or 0.0) * 0.1)
            preliminaries.append((preliminary_score, popularity, raw))

        if not preliminaries:
            return TMDbLookupResult(
                status="not_found",
                detail="TMDB returned no sufficiently similar title",
            )

        preliminaries.sort(key=lambda value: (value[0], value[1]), reverse=True)
        candidates: list[_ScoredCandidate] = []
        for _preliminary, popularity, raw in preliminaries[:_SHORTLIST_SIZE]:
            tmdb_id = int(raw["id"])
            details = self._get_json(
                f"/movie/{tmdb_id}",
                {"language": self._language},
            )
            release_date = _parse_date(details.get("release_date") or raw.get("release_date"))
            if release_date is None:
                continue

            title_similarity = _candidate_title_similarity(requested_normalized, details)
            runtime_similarity = _runtime_similarity(duration_seconds, details.get("runtime"))
            overview_similarity = _text_similarity(
                description,
                details.get("overview") or raw.get("overview"),
            )
            confidence = _weighted_confidence(
                title_similarity=title_similarity,
                runtime_similarity=runtime_similarity,
                overview_similarity=overview_similarity,
            )
            display_title = str(details.get("title") or raw.get("title") or requested_title)
            candidates.append(_ScoredCandidate(
                tmdb_id=tmdb_id,
                title=display_title,
                release_date=release_date,
                confidence=confidence,
                title_similarity=title_similarity,
                popularity=popularity,
            ))

        if not candidates:
            return TMDbLookupResult(
                status="not_found",
                detail="TMDB returned no matching movie with a release date",
            )

        candidates.sort(key=lambda value: (value.confidence, value.popularity), reverse=True)
        best = candidates[0]
        if best.title_similarity < _MIN_TITLE_SIMILARITY or best.confidence < _MIN_MATCH_CONFIDENCE:
            return TMDbLookupResult(
                status="not_found",
                detail=f"The closest TMDB result was not a confident match ({best.title!r})",
            )

        if len(candidates) > 1:
            runner_up = candidates[1]
            if best.confidence - runner_up.confidence < _AMBIGUITY_MARGIN:
                return TMDbLookupResult(
                    status="ambiguous",
                    detail=(
                        "TMDB returned multiple similarly likely matches: "
                        f"{best.title!r} and {runner_up.title!r}"
                    ),
                )

        return TMDbLookupResult(
            status="matched",
            match=TMDbMovieMatch(
                tmdb_id=best.tmdb_id,
                title=best.title,
                release_date=best.release_date,
                confidence=best.confidence,
            ),
        )

    def _get_json(
        self,
        path: str,
        params: Optional[Mapping[str, object]] = None,
    ) -> dict[str, Any]:
        query = urlencode(params or {})
        url = f"{self._base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "User-Agent": self._user_agent,
            },
        )

        for attempt in range(self._max_retries + 1):
            try:
                with urlopen(request, timeout=self._timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise TMDbAPIError("TMDB returned an unexpected response shape")
                return payload
            except HTTPError as exc:
                if exc.code in _TRANSIENT_HTTP_CODES and attempt < self._max_retries:
                    time.sleep(_retry_delay_seconds(exc, attempt))
                    continue
                raise TMDbAPIError(f"TMDB request failed with HTTP {exc.code}") from exc
            except URLError as exc:
                if attempt < self._max_retries:
                    time.sleep(min(2 ** attempt, 5))
                    continue
                raise TMDbAPIError(f"TMDB request failed: {exc.reason}") from exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TMDbAPIError("TMDB returned invalid JSON") from exc

        raise TMDbAPIError("TMDB request failed")


def lookup_movie_release_metadata(
    *,
    title: str,
    description: Optional[str] = None,
    duration_seconds: float = 0,
) -> Optional[MovieReleaseLookupResult]:
    """Perform one TMDB lookup, or return ``None`` when TMDB is not configured."""
    settings = get_settings()
    metadata_settings = settings.movie_metadata
    token_setting = metadata_settings.tmdb_read_access_token
    token = token_setting.get_secret_value().strip() if token_setting is not None else ""
    if not token:
        logger.warning(
            "Movie release-date lookup skipped for %r because no TMDB API Read Access Token is configured",
            title,
        )
        return None

    attempted_at = datetime.now(timezone.utc)
    client = TMDbClient(
        access_token=token,
        base_url=metadata_settings.tmdb_api_base_url,
        language=metadata_settings.language,
        timeout_seconds=metadata_settings.request_timeout_seconds,
        max_retries=metadata_settings.max_retries,
        user_agent=f"WireLoft/{settings.app_version}",
    )
    try:
        result = client.lookup_movie(
            title=title,
            description=description,
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        message = _truncate_error(str(exc))
        logger.warning("TMDB movie metadata lookup failed for %r: %s", title, message)
        return MovieReleaseLookupResult(
            status="error",
            attempted_at=attempted_at,
            error=message,
        )

    if result.status != "matched" or result.match is None:
        detail = _truncate_error(result.detail or "No confident TMDB movie match was found")
        logger.warning(
            "TMDB movie metadata lookup for %r finished as %s: %s",
            title,
            result.status,
            detail,
        )
        return MovieReleaseLookupResult(
            status=result.status,
            attempted_at=attempted_at,
            error=detail,
        )

    match = result.match
    logger.info(
        "Matched Daily Wire movie %r to TMDB movie %s (%r), release date %s",
        title,
        match.tmdb_id,
        match.title,
        match.release_date.isoformat(),
    )
    return MovieReleaseLookupResult(
        status="matched",
        attempted_at=attempted_at,
        release_date=match.release_date,
        source="tmdb",
        source_id=str(match.tmdb_id),
    )


def _normalize_title(value: object) -> str:
    text = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    text = text.casefold().replace("&", " and ")
    return " ".join(_WORD.findall(text))


def _candidate_title_similarity(
    requested_normalized: str,
    candidate: Mapping[str, Any],
) -> float:
    similarities = []
    for key in ("title", "original_title"):
        normalized = _normalize_title(candidate.get(key))
        if normalized:
            similarities.append(
                SequenceMatcher(None, requested_normalized, normalized).ratio()
            )
    return max(similarities, default=0.0)


def _runtime_similarity(
    duration_seconds: float,
    runtime_minutes: object,
) -> Optional[float]:
    if (
        duration_seconds <= 0
        or not isinstance(runtime_minutes, (int, float))
        or runtime_minutes <= 0
    ):
        return None
    difference_seconds = abs(float(duration_seconds) - (float(runtime_minutes) * 60.0))
    return max(0.0, 1.0 - (difference_seconds / (20.0 * 60.0)))


def _text_similarity(left: Optional[str], right: object) -> Optional[float]:
    if not left or not isinstance(right, str) or not right.strip():
        return None
    left_tokens = {
        token
        for token in _WORD.findall(_normalize_title(left))
        if token not in _STOP_WORDS
    }
    right_tokens = {
        token
        for token in _WORD.findall(_normalize_title(right))
        if token not in _STOP_WORDS
    }
    if not left_tokens or not right_tokens:
        return None
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _weighted_confidence(
    *,
    title_similarity: float,
    runtime_similarity: Optional[float],
    overview_similarity: Optional[float],
) -> float:
    weighted = [(title_similarity, 0.70)]
    if runtime_similarity is not None:
        weighted.append((runtime_similarity, 0.20))
    if overview_similarity is not None:
        weighted.append((overview_similarity, 0.10))
    total_weight = sum(weight for _value, weight in weighted)
    return sum(value * weight for value, weight in weighted) / total_weight


def _parse_date(value: object) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _as_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _retry_delay_seconds(exc: HTTPError, attempt: int) -> float:
    retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 10.0)
        except ValueError:
            pass
    return min(2 ** attempt, 5)


def _truncate_error(message: str, limit: int = 1000) -> str:
    normalized = message.strip() or "Unknown TMDB metadata lookup error"
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."
