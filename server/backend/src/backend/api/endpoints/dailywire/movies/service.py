from __future__ import annotations

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwMovieRecord
from dailywire_authorisation import DeviceAuthClient


def get_movie(movie_slug: str) -> DwMovieRecord:
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    return client.get_movie_page(movie_slug)
