from dailywire_api.dw_api.client import MiddlewareAPIError
from dailywire_api.records.DwShowRecord import ProbableShowType


def test_catalog_classifications_reuse_dw_show_model_result(monkeypatch):
    from backend.api.endpoints.dailywire.shows import service

    service._show_type_cache.clear()
    calls: list[str] = []

    class FakeShow:
        def __init__(self, probable_show_type: ProbableShowType):
            self.probable_show_type = probable_show_type

    class FakeClient:
        def get_show_page(self, *, slug: str):
            calls.append(slug)
            return FakeShow(
                ProbableShowType.podcast if slug == 'podcast-show' else ProbableShowType.series
            )

    monkeypatch.setattr(service, '_middleware_client', lambda: FakeClient())

    classifications = service.get_show_type_classifications([
        'podcast-show',
        'series-show',
        'podcast-show',
    ])

    assert classifications == {
        'podcast-show': ProbableShowType.podcast,
        'series-show': ProbableShowType.series,
    }
    assert calls == ['podcast-show', 'series-show']

    # A second browser request should use the cached model results rather than
    # fetching and reclassifying the same Daily Wire shows again.
    assert service.get_show_type_classifications(['series-show', 'podcast-show']) == {
        'series-show': ProbableShowType.series,
        'podcast-show': ProbableShowType.podcast,
    }
    assert calls == ['podcast-show', 'series-show']


def test_catalog_classification_failure_is_unknown_and_not_cached(monkeypatch):
    from backend.api.endpoints.dailywire.shows import service

    service._show_type_cache.clear()
    calls = 0

    class FakeClient:
        def get_show_page(self, *, slug: str):
            nonlocal calls
            calls += 1
            raise MiddlewareAPIError('temporarily unavailable')

    monkeypatch.setattr(service, '_middleware_client', lambda: FakeClient())

    assert service.get_show_type_classifications(['unavailable-show']) == {
        'unavailable-show': ProbableShowType.unknown,
    }
    assert service.get_show_type_classifications(['unavailable-show']) == {
        'unavailable-show': ProbableShowType.unknown,
    }
    assert calls == 2
