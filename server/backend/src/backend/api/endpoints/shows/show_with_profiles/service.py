from __future__ import annotations

from backend.api.endpoints.podcast_download_profiles.service import create_download_profile_podcast
from backend.api.endpoints.media_profiles.service import create_media_profile, update_media_profile
from backend.api.endpoints.shows.service import create_show
from backend.api.models.show import ShowAPIRead
from backend.api.models.show_with_profiles import ShowAPICreateBundle

from backend.app import db_session


def create_show_bundle(payload: ShowAPICreateBundle) -> ShowAPIRead:
    with db_session() as s:
        show = create_show(payload.show)  # should raise 409 on slug conflict
        create_download_profile_podcast(payload.download_profile)

        mp_input = payload.media_profile
        if mp_input.op == "create_new":
            create_media_profile(mp_input)

        elif mp_input.op == "update_by_slug":
            update_media_profile(mp_input.slug, mp_input)

        return show
