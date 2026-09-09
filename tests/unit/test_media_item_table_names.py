def test_concrete_media_item_models_use_prefixed_tables():
    import backend.db.models  # noqa: F401
    from backend.db.models import Episode, Movie, MovieExtra

    assert Episode.__tablename__ == "media_items_episodes"
    assert Movie.__tablename__ == "media_items_movies"
    assert MovieExtra.__tablename__ == "media_items_movie_extras"

    movie_extra_movie_fk = next(iter(MovieExtra.__table__.c.movie_id.foreign_keys))
    official_trailer_fk = next(iter(Movie.__table__.c.official_trailer_id.foreign_keys))

    assert movie_extra_movie_fk.target_fullname == "media_items_movies.id"
    assert official_trailer_fk.target_fullname == "media_items_movie_extras.id"
