def test_movie_promotional_metadata_is_not_persisted_or_exposed():
    import backend.db.models  # noqa: F401
    from backend.api.models.movie import MovieAPICreate, MovieAPIRead, MovieAPIUpdate
    from backend.db.models import Movie

    promotional_fields = {"more_like_this", "shop_items"}

    assert promotional_fields.isdisjoint(Movie.__table__.columns.keys())
    assert promotional_fields.isdisjoint(MovieAPICreate.model_fields)
    assert promotional_fields.isdisjoint(MovieAPIUpdate.model_fields)
    assert promotional_fields.isdisjoint(MovieAPIRead.model_fields)
