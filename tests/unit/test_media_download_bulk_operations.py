from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    ("operation_name", "kind", "action"),
    [
        ("BulkRetryMediaDownloadsOperation", "media_download.bulk_retry", "retry"),
        ("BulkCancelMediaDownloadsOperation", "media_download.bulk_cancel", "cancel"),
        ("BulkDeleteMediaDownloadsOperation", "media_download.bulk_delete", "delete"),
    ],
)
def test_bulk_media_download_operation_targets_are_filter_snapshot_workers(
        operation_name: str,
        kind: str,
        action: str,
):
    from backend.api.endpoints.media_downloads import operations

    operation_type = getattr(operations, operation_name)
    definition = operation_type([8, 3, 8])
    targets = definition.targets()

    assert definition.kind == kind
    assert definition.resource_type == "media_download"
    assert definition.resource_id is None
    assert definition.title == "Downloads"
    assert definition.context() == {"downloads_requested": 2}
    assert definition.media_download_ids == (8, 3)

    assert [target.slot_key for target in targets] == ["media_download:8", "media_download:3"]
    assert all(target.task_key == "media_download_bulk_action_worker" for target in targets)
    assert all(target.resource_type == "media_download" for target in targets)
    # The target deliberately does not own the row. Delete actions remove that row,
    # and HasTaskResourcesMixin must therefore not cascade this operation/run away.
    assert all(target.resource_id is None for target in targets)
    assert [target.task_kwargs for target in targets] == [
        {"media_download_id": 8, "action": action},
        {"media_download_id": 3, "action": action},
    ]
