from __future__ import annotations

from typing import Any, Optional

from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord

from .client import MiddlewareAPIError, MiddlewareClient


class MovieMiddlewareClient(MiddlewareClient):
    """Daily Wire client for the current movie metadata contract.

    ``v4/getMoviePage`` is the canonical metadata source used by WireLoft. Movie
    playback intentionally remains separate: Daily Wire's own current web player
    still obtains the signed movie stream through ``v2/getVideo``.
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

    @staticmethod
    def _movie_extra_type(raw: dict[str, Any]) -> str:
        """Map Daily Wire metadata (or, as a fallback, its title) to one stable type."""
        aliases = {
            "behindthescenes": "behindthescenes",
            "makingof": "behindthescenes",
            "deleted": "deleted",
            "deletedscene": "deleted",
            "deletedscenes": "deleted",
            "featurette": "featurette",
            "interview": "interview",
            "scene": "scene",
            "clip": "scene",
            "short": "short",
            "shortfilm": "short",
            "trailer": "trailer",
            "teaser": "trailer",
            "other": "other",
        }
        for field in ("movieExtraType", "extraType", "contentType"):
            value = "".join(
                character
                for character in str(raw.get(field) or "").casefold()
                if character.isalnum()
            )
            if value in aliases:
                return aliases[value]

        title = str(raw.get("title") or "").casefold()
        compact_title = "".join(
            character if character.isalnum() else " " for character in title
        )
        words = f" {compact_title} "
        if "behind the scenes" in title or "behind-the-scenes" in title or "making of" in title:
            return "behindthescenes"
        if "deleted scene" in title:
            return "deleted"
        if "featurette" in title:
            return "featurette"
        if "interview" in title:
            return "interview"
        if "trailer" in title or "teaser" in title:
            return "trailer"
        if "short film" in title or " short " in words:
            return "short"
        if " scene " in words or " clip " in words:
            return "scene"
        return "other"
