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
                    "host": {"name": "Movie Host", "slug": "movie-host"},
                    "backgroundImage": "background.jpg",
                    "images": {"thumbnail": {
                        "land": "landscape.jpg",
                        "port": "portrait.jpg",
                        "square": "square.jpg",
                    }},
                }},
            ],
        }],
    }

    client = MiddlewareClient(base_url="https://example.invalid", pace_requests=False)
    monkeypatch.setattr(client, "_get", lambda endpoint, params: payload)

    catalog = client.get_catalog()

    assert [show.title for show in catalog.shows] == ["Real History with Matt Walsh"]
    assert catalog.shows[0].description == show_description

    movie = catalog.movies[0]
    assert movie.title == "Sample Movie"
    assert movie.extended_title == f"Sample Movie | {movie_description}"
    assert movie.author_name == "Movie Host"
    assert movie.author_slug == "movie-host"
    assert movie.background_image_path == "background.jpg"
    assert movie.thumbnail_landscape_path == "landscape.jpg"
    assert movie.thumbnail_portrait_path == "portrait.jpg"
    assert movie.thumbnail_square_path == "square.jpg"
