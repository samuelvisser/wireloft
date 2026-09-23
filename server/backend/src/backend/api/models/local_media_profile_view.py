from __future__ import annotations

from typing import Annotated

from pydantic import Field

from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPIRead
from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPIRead


LocalMediaProfileAPIRead = Annotated[
    ShowLocalMediaProfileAPIRead | MovieLocalMediaProfileAPIRead,
    Field(discriminator="type"),
]
