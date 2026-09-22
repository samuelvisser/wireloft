from __future__ import annotations

from datetime import datetime, timezone


def _show_payload(*, land, port, square):
    return {
        "show": {
            "id": "show-1",
            "slug": "example-show",
            "title": "Example Show",
            "sharingURL": "https://www.dailywire.com/show/example-show",
            "images": {
                "thumbnail": {
                    "land": land,
                    "port": port,
                    "square": square,
                },
            },
            "latestEpisode": {
                "id": "episode-1",
                "slug": "example-episode",
                "title": "Example Episode",
                "duration": 60,
                "sharingURL": "https://www.dailywire.com/episode/example-episode",
                "status": "published",
                "isDownloadable": True,
                "publishedAt": datetime(2026, 9, 22, tzinfo=timezone.utc),
            },
        },
        "selectedSeason": {
            "id": "season-1",
            "name": "2026",
            "slug": "2026",
        },
    }


def _episode_payload(*, land, port, square):
    return {
        "id": "episode-1",
        "slug": "example-episode",
        "title": "Example Episode",
        "duration": 60,
        "sharingURL": "https://www.dailywire.com/episode/example-episode",
        "status": "published",
        "isDownloadable": True,
        "publishedAt": datetime(2026, 9, 22, tzinfo=timezone.utc),
        "images": {
            "thumbnail": {
                "land": land,
                "port": port,
                "square": square,
            },
        },
    }


def test_show_record_keeps_portrait_and_discards_duplicate_landscape_and_square():
    from dailywire_api.records import DwShowRecord

    record = DwShowRecord.model_validate(
        _show_payload(
            land="portrait.jpg",
            port="portrait.jpg",
            square="portrait.jpg",
        )
    )

    assert record.thumbnail_portrait_path == "portrait.jpg"
    assert record.thumbnail_landscape_path is None
    assert record.thumbnail_square_path is None


def test_show_record_preserves_distinct_landscape_and_square_urls():
    from dailywire_api.records import DwShowRecord

    record = DwShowRecord.model_validate(
        _show_payload(
            land="image.jpg",
            port="image.jpg?auto=compress",
            square="square.jpg",
        )
    )

    assert record.thumbnail_portrait_path == "image.jpg?auto=compress"
    assert record.thumbnail_landscape_path == "image.jpg"
    assert record.thumbnail_square_path == "square.jpg"


def test_catalog_show_record_uses_same_thumbnail_normalization():
    from dailywire_api.records import DwCatalogShowRecord

    record = DwCatalogShowRecord(
        dw_id="show-1",
        slug="example-show",
        title="Example Show",
        thumbnail_landscape_path="portrait.jpg",
        thumbnail_portrait_path="portrait.jpg",
        thumbnail_square_path="portrait.jpg",
    )

    assert record.thumbnail_portrait_path == "portrait.jpg"
    assert record.thumbnail_landscape_path is None
    assert record.thumbnail_square_path is None


def test_episode_record_keeps_landscape_and_discards_duplicate_portrait_and_square():
    from dailywire_api.records import DwEpisodeRecord

    record = DwEpisodeRecord.model_validate(
        _episode_payload(
            land="landscape.jpg",
            port="landscape.jpg",
            square="landscape.jpg",
        )
    )

    assert record.thumbnail_landscape_path == "landscape.jpg"
    assert record.thumbnail_portrait_path is None
    assert record.thumbnail_square_path is None


def test_episode_record_preserves_distinct_portrait_and_square_urls():
    from dailywire_api.records import DwEpisodeRecord

    record = DwEpisodeRecord.model_validate(
        _episode_payload(
            land="image.jpg",
            port="image.jpg?auto=compress",
            square="square.jpg",
        )
    )

    assert record.thumbnail_landscape_path == "image.jpg"
    assert record.thumbnail_portrait_path == "image.jpg?auto=compress"
    assert record.thumbnail_square_path == "square.jpg"
