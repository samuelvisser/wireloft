from __future__ import annotations


def test_movie_metadata_is_owned_by_movie_client_and_uses_get_movie_page(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    assert not hasattr(MiddlewareClient, "get_movie_page")

    client = MovieMiddlewareClient(base_url="https://middleware.example/middleware")
    calls: list[tuple[str, dict]] = []

    def fake_get(endpoint, params):
        calls.append((endpoint, params))
        return {
            "id": "movie-1",
            "slug": "a-movie",
            "title": "A Movie",
            "description": "Movie description",
            "duration": 5400,
            "sharingURL": "https://www.dailywire.com/videos/a-movie",
            "status": "published",
            "hasVideo": True,
            "isDownloadable": True,
            "extras": [
                {
                    "id": "extra-1",
                    "slug": "behind-the-scenes",
                    "title": "Behind the Scenes",
                    "extraType": "BehindTheScenes",
                }
            ],
            "trailer": {
                "id": "trailer-1",
                "slug": "a-movie-trailer",
                "title": "A Movie | Official Trailer",
                "trailerURL": "https://stream.example/trailer.m3u8",
            },
        }

    monkeypatch.setattr(client, "_get", fake_get)

    movie = client.get_movie_page("a-movie", membership_plan="ALL_ACCESS")

    assert calls == [(
        "v4/getMoviePage",
        {"slug": "a-movie", "membershipPlan": "ALL_ACCESS"},
    )]
    assert movie.slug == "a-movie"
    assert movie.trailer is not None
    assert movie.trailer.slug == "a-movie-trailer"
    assert {extra.slug for extra in movie.movie_extras} == {
        "behind-the-scenes",
        "a-movie-trailer",
    }


def test_movie_playback_intentionally_uses_v2_get_video(monkeypatch):
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    client = MovieMiddlewareClient(base_url="https://middleware.example/middleware")
    calls: list[tuple[str, dict]] = []

    def fake_get(endpoint, params):
        calls.append((endpoint, params))
        return {
            "video": {
                "hasVideo": True,
                "videoURL": "https://stream.example/movie/master.m3u8",
                "duration": 5400,
            }
        }

    monkeypatch.setattr(client, "_get", fake_get)

    playback = client.get_movie_playback("a-movie")

    assert calls == [("v2/getVideo", {"slug": "a-movie"})]
    assert playback.has_video is True
    assert playback.video_url == "https://stream.example/movie/master.m3u8"
    assert playback.duration == 5400


def test_movie_extra_playback_uses_clip_endpoint_and_retains_metadata(monkeypatch):
    from dailywire_api.dw_api.movie import MovieMiddlewareClient

    client = MovieMiddlewareClient(base_url="https://middleware.example/middleware")
    calls: list[tuple[str, dict]] = []
    thumbnail_url = (
        "https://daily-wire-production.imgix.net/clips/example/"
        "John%20Matthews%20Thumbnail.png?auto=compress&cs=origin"
    )

    def fake_get(endpoint, params):
        calls.append((endpoint, params))
        return {
            "id": "extra-1",
            "slug": "making-of-a-movie",
            "title": "The Making of A Movie",
            "description": "Fresh clip metadata",
            "duration": 600,
            "publishedAt": "2026-09-16T19:27:02.570Z",
            "sharingURL": "https://www.dailywire.com/clips/making-of-a-movie",
            "availableFor": ["FREE", "ALL_ACCESS"],
            "images": {
                "thumbnail": {
                    "land": thumbnail_url,
                    "port": thumbnail_url,
                    "square": "",
                }
            },
            "videoURL": "https://stream.example/extra/master.m3u8",
        }

    monkeypatch.setattr(client, "_get", fake_get)

    playback = client.get_movie_extra_playback("making-of-a-movie")

    assert calls == [("v4/getClip", {"slug": "making-of-a-movie"})]
    assert playback.has_video is True
    assert playback.video_url == "https://stream.example/extra/master.m3u8"
    assert playback.metadata.slug == "making-of-a-movie"
    assert playback.metadata.thumbnail_landscape_path == thumbnail_url
    assert playback.metadata.thumbnail_portrait_path == thumbnail_url
    assert playback.metadata.thumbnail_square_path == ""
    assert playback.metadata.sharing_url == "https://www.dailywire.com/clips/making-of-a-movie"
    assert playback.metadata.available_for == ["FREE", "ALL_ACCESS"]
