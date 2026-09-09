from __future__ import annotations

from typing import Any, Optional

from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord

from .client import MiddlewareAPIError, MiddlewareClient


class MovieMiddlewareClient(MiddlewareClient):
    """Daily Wire client for the current v4 movie-page contract.

    Daily Wire's ``getMoviePage`` response is already the canonical, flattened
    movie representation used by its current website. Keep the compatibility
    adapter here so the rest of WireLoft consumes one typed ``DwMovieRecord``
    instead of reconstructing movie metadata from the older video-page tabs.
    """

    def get_movie_page(
        self,
        slug: str,
        *,
        membership_plan: Optional[str] = None,
    ) -> DwMovieRecord:
        params: dict[str, Any] = {"slug": slug}
        if membership_plan:
            params["membershipPlan"] = membership_plan

        payload = self._get("v4/getMoviePage", params)
        if not isinstance(payload, dict) or not payload.get("slug"):
            raise MiddlewareAPIError(f"Daily Wire movie '{slug}' was not found")

        extras: list[DwMovieExtraRecord] = []
        for raw_extra in payload.get("extras") or []:
            if not isinstance(raw_extra, dict) or not raw_extra.get("slug"):
                continue
            extras.append(DwMovieExtraRecord.model_validate({
                **raw_extra,
                "movieExtraType": self._movie_extra_type(raw_extra),
            }))

        raw_trailer = payload.get("trailer")
        trailer = (
            DwMovieExtraRecord.model_validate({
                **raw_trailer,
                "movieExtraType": "trailer",
            })
            if isinstance(raw_trailer, dict) and raw_trailer.get("slug")
            else None
        )

        # The dedicated trailer object contains fresh playback fields but omits
        # some descriptive fields (notably availableFor) that exist on the same
        # row in extras. Daily Wire entity IDs can rotate, so the immutable slug
        # is the only identity used when merging those two API representations.
        if trailer is not None:
            matched = False
            for index, extra in enumerate(extras):
                if extra.slug == trailer.slug:
                    trailer = trailer.model_copy(update={
                        "available_for": list(extra.available_for),
                    })
                    extras[index] = trailer
                    matched = True
                    break
            if not matched:
                extras.insert(0, trailer)

        return DwMovieRecord.model_validate({
            **payload,
            "movie_extras": extras,
            "trailer": trailer,
        })
