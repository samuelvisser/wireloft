from __future__ import annotations


def test_dailywire_catalog_normalizes_show_and_movie_titles(monkeypatch):
    from dailywire_api.dw_api.client import MiddlewareClient

    show_description = (
        "Matt Walsh confronts the lies used to rewrite America's past. "
        "It challenges decades of propaganda."
    )
    movie_description = "A long marketing description."
    payload = {
        "components": [{
            "items": [
                {"show": {
                    "id": "show-1",
                    "slug": "real-history-with-matt-walsh",
                    "title": f"Real History with Matt Walsh | {show_description}",
                    "description": show_description,
                }},
                {"video": {
                    "id": "movie-1",
                    "slug": "sample-movie",
                    "title": f"Sample Movie | {movie_description}",
                    "description": movie_description,
                }},
            ],
        }],
    }

    client = MiddlewareClient(base_url="https://example.invalid", pace_requests=False)
    monkeypatch.setattr(client, "_get", lambda endpoint, params: payload)

    catalog = client.get_catalog()

    assert [show.title for show in catalog.shows] == ["Real History with Matt Walsh"]
    assert catalog.shows[0].description == show_description
    assert [movie.title for movie in catalog.movies] == ["Sample Movie"]
    assert catalog.movies[0].extended_title == f"Sample Movie | {movie_description}"
