"""Media-domain adapters for the shared, database-independent Jinja analysis."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from jinja2 import Environment, nodes

from .jinja_analysis import TemplateAnalysis, analyze_template
from .jinja_analysis.comparison import OutputComparison, OutputOverlap, compare_outputs


# Only aliases guaranteed by episode_output_template_values are equivalent.
_SHOW_ALIASES = {
    "title": "episode_title",
    "episode_published_date": "date",
    "episode_published_time": "time",
    "episode_published_datetime": "datetime",
}
_MOVIE_ALIASES = {
    "slug": "movie_slug", "title": "movie_title", "extended_title": "movie_extended_title",
    "author": "movie_author", "mature_rating": "movie_mature_rating", "rating": "movie_mature_rating",
    "duration_seconds": "movie_duration_seconds",
    **{name: f"movie_{name}" for name in (
        "date", "time", "datetime", "year", "month", "day", "hour", "minute", "second",
    )},
}


@dataclass(frozen=True)
class ProfileOutputAnalysis:
    profile_type: str
    extension: str
    scenarios: tuple[TemplateAnalysis, ...]


def analyze_profile_outputs(
    template: str,
    profile_type: str,
    preferred_format: str,
    *,
    environment: Environment,
    namespace: str,
) -> ProfileOutputAnalysis:
    """Analyze Show profiles, or separately analyze movie features and extras.

    Movie parent/item aliases coincide for the feature, but NOT for its extras.
    Local custom indexes remain profile-scoped symbols and are never evaluated.
    """
    extension = {"format_audio_only": "m4a", "format_hls": "m3u8"}.get(preferred_format, "mp4")
    if profile_type == "show":
        scenarios = (analyze_template(template, environment=environment, aliases=_SHOW_ALIASES, namespace=namespace),)
    elif profile_type == "movie":
        feature = analyze_template(template, environment=environment, aliases=_MOVIE_ALIASES,
                                   known_values={"media_type": "movie"}, namespace=namespace)
        extra = analyze_template(
            template, environment=environment, aliases={"extended_title": "title"},
            known_values={"author": "", "rating": "", "mature_rating": ""},
            assumptions=((nodes.Compare(nodes.Name("media_type", "load"), [nodes.Operand("ne", nodes.Const("movie"))]), True),),
            namespace=namespace,
        )
        scenarios = (feature, extra)
    else:
        raise ValueError("Output analysis requires a Show or Movie Local Media Profile")
    return ProfileOutputAnalysis(profile_type, extension, scenarios)


def compare_profile_outputs(
    left: ProfileOutputAnalysis,
    right: ProfileOutputAnalysis,
    *,
    environment: Environment,
    finalize_path: Callable[[str, str], str],
) -> OutputComparison:
    """Compare the same media input, applying the real final filename policy."""
    if left.profile_type != right.profile_type or left.extension != right.extension:
        return OutputComparison(OutputOverlap.DISJOINT)
    uncertain = None
    for lhs, rhs in zip(left.scenarios, right.scenarios, strict=True):
        result = compare_outputs(lhs, rhs, environment=environment,
                                 finalize_left=lambda path: finalize_path(path, left.extension),
                                 finalize_right=lambda path: finalize_path(path, right.extension))
        if result.status == OutputOverlap.OVERLAP:
            return result
        if result.status == OutputOverlap.UNKNOWN:
            uncertain = result
    return uncertain or OutputComparison(OutputOverlap.DISJOINT)
