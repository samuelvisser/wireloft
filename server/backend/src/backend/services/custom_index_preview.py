"""Plan Custom Index preview work before any historical episode simulation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CustomIndexState, Episode, ShowLocalMediaProfile
from backend.services.custom_indexes import profile_applies_to_show
from backend.utils.custom_index import (
    get_episode_index_assignments,
    indexing_value_definition_keys,
)
from backend.utils.jinja_analysis.custom_indexes import (
    CustomIndexReachabilityStatus,
    compare_custom_index_reachability,
)
from backend.utils.output_template import (
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    episode_output_template_values,
    output_template_custom_index_keys,
)
from backend.utils.output_template_jinja import create_output_template_environment


class CustomIndexPreviewMode(StrEnum):
    NONE = "none"
    UNDEFINED_ONLY = "undefined_only"
    USE_PERSISTED = "use_persisted"
    SIMULATE = "simulate"


@dataclass(frozen=True)
class CustomIndexPreviewPlan:
    mode: CustomIndexPreviewMode
    referenced_keys: frozenset[str]
    active_keys: frozenset[str]
    missing_keys: frozenset[str]
    persisted_assignments: dict[str, int]
    reason: str | None = None

    @property
    def simulates(self) -> bool:
        return self.mode == CustomIndexPreviewMode.SIMULATE


def plan_custom_index_preview(
    session: Session | None,
    *,
    draft_template: str,
    draft_definition_keys: frozenset[str],
    episode: Episode | None,
    local_media_profile_id: int | None,
    draft_values: dict[str, str],
    referenced_keys: frozenset[str] | None = None,
) -> CustomIndexPreviewPlan:
    """Choose the cheapest safe source for Custom Index values in a draft preview.

    Persisted assignments are reused immediately when the saved template and
    example values are unchanged. Otherwise the analyzer must prove that every
    active draft key has the same episode-reachability predicate as the saved
    template and none of those predicates depends on an edited example value.
    Any unprovable case deliberately falls back to historical simulation.
    """
    referenced = referenced_keys if referenced_keys is not None else output_template_custom_index_keys(draft_template)
    active = referenced & draft_definition_keys
    missing = referenced - draft_definition_keys
    if not referenced:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.NONE, referenced, active, missing, {},
        )
    if not active:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.UNDEFINED_ONLY, referenced, active, missing, {},
        )
    if session is None or episode is None or local_media_profile_id is None:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            "No saved episode/profile assignment state is available",
        )

    profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
    if profile is None or not profile_applies_to_show(profile, episode.show):
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            "The selected show has no reusable saved assignments for this profile",
        )

    saved_definitions = indexing_value_definition_keys(profile)
    saved_keys = output_template_custom_index_keys(profile.output_template)
    if not active <= saved_definitions or not active <= saved_keys:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            "One or more draft indexes do not have saved assignment history",
        )

    state = session.scalar(select(CustomIndexState).where(
        CustomIndexState.show_id == episode.show_id,
        CustomIndexState.local_media_profile_id == profile.id,
    ))
    if state is None or state.completed_generation != state.requested_generation:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            "Saved Custom Index assignments are not current",
        )

    original_values = episode_output_template_values(episode)
    values_unchanged = all(
        draft_values.get(key, "") == original_values.get(key, "")
        for key in set(draft_values) | set(original_values)
    )
    if profile.output_template == draft_template and values_unchanged:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.USE_PERSISTED,
            referenced,
            active,
            missing,
            get_episode_index_assignments(episode, profile.id),
        )

    environment = create_output_template_environment()
    comparison = compare_custom_index_reachability(
        profile.output_template,
        draft_template,
        environment=environment,
        keys=active,
    )
    if comparison.status != CustomIndexReachabilityStatus.UNCHANGED:
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            comparison.reason or "Custom Index assignment conditions changed",
        )

    if any(
        draft_values.get(dependency, original_values.get(dependency, ""))
        != original_values.get(dependency, "")
        for dependency in comparison.dependencies
        if dependency in SHOW_OUTPUT_TEMPLATE_FIELDS or dependency.startswith("meta_show_")
    ):
        return CustomIndexPreviewPlan(
            CustomIndexPreviewMode.SIMULATE, referenced, active, missing, {},
            "An edited example value affects Custom Index assignment conditions",
        )

    return CustomIndexPreviewPlan(
        CustomIndexPreviewMode.USE_PERSISTED,
        referenced,
        active,
        missing,
        get_episode_index_assignments(episode, profile.id),
    )
