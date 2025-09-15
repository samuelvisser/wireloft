from __future__ import annotations

from typing import Optional

from dailywire_api.dw_api.client import MiddlewareClient, MiddlewareAPIError
from dailywire_api.records import ShowRecord


def get_show(
    show_slug: str,
    *,
    access_token: Optional[str] = None,
    membership_plan: Optional[str] = None,
) -> ShowRecord:
    """Fetch a DailyWire show by slug from the middleware API and normalize it.

    Parameters
    - show_slug: The DailyWire show slug (e.g., "the-ben-shapiro-show").
    - access_token: Optional JWT bearer token for premium content.
    - membership_plan: Optional membership plan that can affect content selection.
    """
    client = MiddlewareClient(access_token=access_token)
    payload = client.get_show_page(slug=show_slug, membership_plan=membership_plan)

    # Map the normalized ShowRecord payload into our response model
    return ShowRecord.model_validate(payload)
