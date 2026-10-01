from fastapi import APIRouter, HTTPException, status

from backend.api.models.operations import TaskOperationAccepted
from backend.api.models.settings import SettingsAPIRead, SettingsAPIUpdate
from backend.app import db_session
from backend.services.show_assets import request_show_asset_reconciliation
from .service import (
    SettingsManagedByEnvironmentError,
    SettingsPersistenceError,
    get_ui_settings,
    save_ui_settings,
    run_cron_job_now,
)


router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("", response_model=SettingsAPIRead)
def settings_get():
    """Return all settings intentionally exposed by the WireLoft UI."""
    return get_ui_settings()


@router.put("", response_model=SettingsAPIRead)
def settings_update(body: SettingsAPIUpdate):
    """Persist only explicitly changed UI fields into config.yml."""
    try:
        result = save_ui_settings(body)
    except SettingsManagedByEnvironmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SettingsPersistenceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if set(body.changed_fields) & {
        "downloadSettings.downloadShowAssets", "downloadSettings.showArtworkFallbackFormat",
        "downloadSettings.downloadRoot", "downloadSettings.filenameRestrictionMode",
        "downloadSettings.ffmpegPath",
    }:
        with db_session() as session:
            request_show_asset_reconciliation(session)
            session.commit()
    return result


@router.post(
    "/cron/{job}/run",
    response_model=TaskOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def settings_cron_run(job: str):
    """Run one configured cron job immediately as a TaskOperation."""
    with db_session() as session:
        try:
            result = run_cron_job_now(session, job)
            session.commit()
            return result
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception:
            session.rollback()
            raise
