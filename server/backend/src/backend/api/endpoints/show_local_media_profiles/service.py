from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.endpoints.local_media_profiles.helpers import ensure_unique_profile_settings
from backend.api.endpoints.local_media_profiles.service import delete_local_media_profile_record
from backend.api.models.show_local_media_profile import (
    ShowLocalMediaProfileAPICreate,
    ShowLocalMediaProfileAPIRead,
    ShowLocalMediaProfileAPIUpdate,
)
from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.db.models import CustomIndexState, Show, ShowLocalMediaProfile
from backend.services.custom_indexes import (
    profile_applies_to_show, profile_uses_custom_indexes, remove_profile_custom_index_state,
    request_custom_index_reconciliation,
)
from backend.utils.custom_index import indexing_value_definition_keys, replace_indexing_value_definitions
from backend.utils.output_template import output_template_custom_index_keys
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)
from task_manager.scheduler.types import OperationSource


def _queue_custom_index_management(
    s: Session,
    profile: ShowLocalMediaProfile,
    *,
    rename_files: bool = False,
) -> str | None:
    existing = set(s.scalars(select(CustomIndexState.show_id).where(
        CustomIndexState.local_media_profile_id == profile.id,
    )))
    show_ids = tuple(sorted(existing | {
        show.id for show in s.scalars(select(Show))
        if profile_applies_to_show(profile, show)
    }))
    if not show_ids:
        if rename_files:
            from backend.api.endpoints.local_media_profiles.file_rename import request_show_local_media_profile_file_rename
            request_show_local_media_profile_file_rename(s, profile.slug)
        return None

    for show_id in show_ids:
        request_custom_index_reconciliation(
            s, show_id=show_id, local_media_profile_id=profile.id, dispatch=False,
        )
    target = OperationTargetSpec(
        task_key="manage_custom_indexes", resource_type="local_media_profile",
        resource_id=profile.id,
        task_kwargs={"rename_after": rename_files, "profile_change_token": uuid4().hex},
    )
    operation = create_operation(
        s,
        kind="local_media_profile.manage_custom_indexes",
        source=OperationSource.UI.value,
        resource_type="local_media_profile",
        resource_id=profile.id,
        title=profile.name,
        targets=[target],
        context={
            "local_media_profile_slug": profile.slug,
            "local_media_profile_name": profile.name,
            "rename_after": rename_files,
        },
    )
    queue_operation_target_dispatch(s, operation.id, target.resolved_slot_key())
    return operation.id


def get_show_local_media_profiles_list(
    s: Session,
) -> list[ShowLocalMediaProfileAPIRead]:
    items = (
        s.query(ShowLocalMediaProfile)
        .order_by(ShowLocalMediaProfile.id)
        .all()
    )
    return [ShowLocalMediaProfileAPIRead.model_validate(item) for item in items]


def get_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")
    return ShowLocalMediaProfileAPIRead.model_validate(item)


def create_show_local_media_profile(
    s: Session,
    body: ShowLocalMediaProfileAPICreate,
) -> ShowLocalMediaProfileAPIRead:
    ensure_unique_profile_settings(s, ShowLocalMediaProfile, body)
    item = create_database_fields(ShowLocalMediaProfile, body)
    s.add(item)
    s.flush()
    replace_indexing_value_definitions(item, body.indexing_values)
    if profile_uses_custom_indexes(item):
        _queue_custom_index_management(s, item)
    return ShowLocalMediaProfileAPIRead.model_validate(item)


def update_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
    body: ShowLocalMediaProfileAPIUpdate,
    *,
    rename_files: bool = False,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")

    previous_template = item.output_template
    previous_index_keys = output_template_custom_index_keys(previous_template)
    previous_definition_keys = indexing_value_definition_keys(item)
    previous_scope = item.show_scope

    ensure_unique_profile_settings(
        s,
        ShowLocalMediaProfile,
        body,
        exclude_id=item.id,
    )
    update_database_fields(item, body, exclude_fields={"indexing_values"})
    replace_indexing_value_definitions(item, body.indexing_values)
    s.flush()

    current_index_keys = output_template_custom_index_keys(item.output_template)
    current_definition_keys = indexing_value_definition_keys(item)
    definition_keys_changed = previous_definition_keys != current_definition_keys
    template_changed = previous_template != item.output_template
    scope_changed = previous_scope != item.show_scope
    needs_custom_index_management = (
        (template_changed or scope_changed or definition_keys_changed)
        and bool(
            previous_index_keys & previous_definition_keys
            or current_index_keys & current_definition_keys
            or s.scalar(select(CustomIndexState.id).where(
                CustomIndexState.local_media_profile_id == item.id,
            ).limit(1)) is not None
        )
    )

    if needs_custom_index_management:
        _queue_custom_index_management(
            s,
            item,
            rename_files=rename_files,
        )
    elif rename_files and (template_changed or definition_keys_changed):
        from backend.api.endpoints.local_media_profiles.file_rename import (
            request_show_local_media_profile_file_rename,
        )
        request_show_local_media_profile_file_rename(s, item.slug)

    return ShowLocalMediaProfileAPIRead.model_validate(item)


def delete_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")

    payload = ShowLocalMediaProfileAPIRead.model_validate(item)
    remove_profile_custom_index_state(
        s,
        local_media_profile_id=item.id,
    )
    delete_local_media_profile_record(s, item)
    return payload
