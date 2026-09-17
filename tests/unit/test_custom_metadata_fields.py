from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def test_custom_metadata_fields_are_scoped_sorted_and_validated(db_session):
    from backend.api.endpoints.custom_metadata_service import get_custom_metadata_fields
    from backend.db.models import Show
    from backend.db.models.Metadata import Metadata
    from backend.db.models.media_item import Movie

    db_session.add_all([
        Metadata(parent_table=Show.__tablename__, parent_id=1, key="custom.zeta", value="one"),
        Metadata(parent_table=Show.__tablename__, parent_id=2, key="custom.alpha", value="two"),
        Metadata(parent_table=Show.__tablename__, parent_id=3, key="custom.BadField", value="ignored"),
        Metadata(parent_table=Show.__tablename__, parent_id=4, key="other.alpha", value="ignored"),
        Metadata(parent_table=Movie.__tablename__, parent_id=1, key="custom.movie_field", value="movie"),
    ])
    db_session.flush()

    assert get_custom_metadata_fields(db_session, "show") == ["alpha", "zeta"]
    assert get_custom_metadata_fields(db_session, "movie") == ["movie_field"]
