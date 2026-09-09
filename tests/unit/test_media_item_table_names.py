def test_concrete_media_item_models_match_media_download_table_naming():
    import backend.db.models  # noqa: F401
    from backend.db.models import Episode, Movie, MovieExtra

    assert Episode.__tablename__ == "media_items_episode"
    assert Movie.__tablename__ == "media_items_movie"
    assert MovieExtra.__tablename__ == "media_items_movie_extra"

    movie_extra_movie_fk = next(iter(MovieExtra.__table__.c.movie_id.foreign_keys))
    official_trailer_fk = next(iter(Movie.__table__.c.official_trailer_id.foreign_keys))

    assert movie_extra_movie_fk.target_fullname == "media_items_movie.id"
    assert official_trailer_fk.target_fullname == "media_items_movie_extra.id"
