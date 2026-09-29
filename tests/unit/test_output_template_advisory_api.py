import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.endpoints.local_media_profiles.advisory import router


@pytest.fixture
def client():
    # The advisory router has no DB/session dependency and works before examples
    # have been seeded. Authentication remains with the parent application.
    app = FastAPI()
    app.include_router(router, prefix='/local-media-profiles')
    with TestClient(app) as client:
        yield client


def request(client, template, keys=('extra',)):
    return client.post('/local-media-profiles/advisory/custom-index', json={
        'outputTemplate': template,
        'indexingValueKeys': list(keys),
    })


def test_advisory_returns_camelcase_suggestion_without_needing_a_saved_profile(client):
    response = request(client, "{% set n='extra'|custom_index %}{% set label='other' ~ n if is_extra else 'normal' %}/downloads/{{label}}.ext")
    assert response.status_code == 200
    body = response.json()
    assert body['error'] is None
    item, = body['advisories']
    assert item['key'] == 'extra'
    assert item['suggestion']['outputTemplate'].startswith('{% set label %}')
    assert 'output_template' not in item['suggestion']


@pytest.mark.parametrize('template', [
    "{% set extra_num='extra' | custom_index e%}/downloads/{{title}}.ext",
    "{% if extra %}",
    "{{",
])
def test_incomplete_typing_returns_200_not_a_backend_exception(client, template):
    response = request(client, template)
    assert response.status_code == 200
    assert response.json()['advisories'] == []
    assert response.json()['error']


def test_undefined_and_no_index_templates_need_no_advice(client):
    for source, keys in [("{{'extra'|custom_index}}", ()), ('/downloads/{{title}}.ext', ('extra',)), ('', ('extra',))]:
        response = request(client, source, keys)
        assert response.status_code == 200
        assert response.json() == {'advisories': [], 'error': None}


def test_unconditional_warning_survives_without_a_suggestion(client):
    response = request(client, "/downloads/{{'extra'|custom_index}}.ext")
    assert response.status_code == 200
    item, = response.json()['advisories']
    assert 'every episode' in item['message']
    assert item['suggestion'] is None


def test_advisory_input_is_bounded(client):
    assert request(client, 'x' * 4097).status_code == 422
    assert request(client, '', [f'key{i}' for i in range(101)]).status_code == 422
