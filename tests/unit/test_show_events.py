from types import SimpleNamespace


def test_show_added_payload_contains_canonical_show_identity():
    from backend.api.endpoints.shows.events import ShowAdded

    show = SimpleNamespace(
        id=42,
        slug="test-show",
        title="Test Show",
    )

    assert ShowAdded(show) == {
        "resource_id": 42,
        "id": 42,
        "slug": "test-show",
        "title": "Test Show",
    }
