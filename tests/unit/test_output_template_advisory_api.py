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
    assert item['kind'] == 'all_episodes'
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
    response = request(client, "{% set n='extra'|custom_index %}/downloads/{{title}}.ext")
    assert response.status_code == 200
    item, = response.json()['advisories']
    assert 'every episode' in item['message']
    assert item['kind'] == 'all_episodes'
    assert item['suggestion'] is None


def test_advisory_input_is_bounded(client):
    assert request(client, 'x' * 4097).status_code == 422
    assert request(client, '', [f'key{i}' for i in range(101)]).status_code == 422


def test_unconditional_output_returns_builtin_episode_index_advice(client):
    response = request(client, (
        "{% set extra_num='extra'|custom_index %}"
        "{% set clean_title=title.replace(' ', '-') %}"
        "/downloads/{{extra_num}} - {{clean_title}}.ext"
    ))
    assert response.status_code == 200
    item, = response.json()['advisories']
    assert item['kind'] == 'episode_index'
    assert 'episode_index' in item['message']
    assert 'episode_index | int' in item['suggestion']['after']
    assert 'custom_index' not in item['suggestion']['outputTemplate']


def test_mixed_advisory_kinds_are_serialized_per_key(client):
    response = request(client, (
        "{% set all='all'|custom_index %}{% set extra='extra'|custom_index %}"
        "/downloads/{{all}}-{{extra if is_extra else 0}}.ext"
    ), keys=('all', 'extra'))
    assert response.status_code == 200
    assert [(item['key'], item['kind']) for item in response.json()['advisories']] == [
        ('all', 'episode_index'), ('extra', 'all_episodes'),
    ]
