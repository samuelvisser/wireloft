from __future__ import annotations

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwCatalogRecord
from dailywire_authorisation import DeviceAuthClient


def get_catalog() -> DwCatalogRecord:
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    return client.get_catalog()
