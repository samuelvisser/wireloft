from types import SimpleNamespace

import pytest

from backend.services import show_assets as assets
from backend.utils.show_media_directory import ShowMediaDirectory


@pytest.mark.parametrize('system,override,expected', [
    (False, None, False), (True, None, True),
    (False, True, True), (True, False, False),
    (False, False, False), (True, True, True),
])
def test_profile_override_inherits_only_when_null(monkeypatch, system, override, expected):
    monkeypatch.setattr(assets, 'get_settings', lambda: SimpleNamespace(
        download_settings=SimpleNamespace(download_show_assets=system),
    ))
    assert assets.show_assets_enabled(SimpleNamespace(download_show_assets=override)) is expected


def test_artwork_source_priorities_and_missing_variants():
    show = SimpleNamespace(
        thumbnail_portrait_path='https://example.invalid/portrait',
        thumbnail_square_path='https://example.invalid/square',
        thumbnail_landscape_path='https://example.invalid/landscape',
        background_image_path='https://example.invalid/background',
    )
    assert dict(assets.show_asset_sources(show)) == {
        'poster': show.thumbnail_portrait_path,
        'fanart': show.background_image_path,
        'square': show.thumbnail_square_path,
    }
    show.thumbnail_portrait_path = None
    show.background_image_path = None
    assert dict(assets.show_asset_sources(show))['poster'] == show.thumbnail_square_path
    assert dict(assets.show_asset_sources(show))['fanart'] == show.thumbnail_landscape_path
    show.thumbnail_square_path = None
    show.thumbnail_landscape_path = 'file:///not-a-remote-image'
    assert assets.show_asset_sources(show) == ()


def test_artwork_metadata_refresh_preserves_absent_variants():
    show = SimpleNamespace(thumbnail_portrait_path='old', thumbnail_square_path='known-square')
    assets.update_show_artwork_metadata(show, SimpleNamespace(thumbnail_portrait_path='new'))
    assert show.thumbnail_portrait_path == 'new'
    assert show.thumbnail_square_path == 'known-square'


def test_preview_uses_selected_episodes_show_and_unsaved_template(monkeypatch):
    show = SimpleNamespace(id=7, title='Actual show')
    session = SimpleNamespace(get=lambda _model, identity: SimpleNamespace(show=show) if identity == 42 else None)
    monkeypatch.setattr(assets, 'get_settings', lambda: SimpleNamespace(
        download_settings=SimpleNamespace(download_show_assets=True),
    ))
    received = []

    def resolve(actual_show, template, *, values_overrides=None):
        received.append((actual_show, template))
        return ShowMediaDirectory('/library/Actual show')

    monkeypatch.setattr(assets, 'resolve_show_media_directory', resolve)
    monkeypatch.setattr(assets, 'show_profile_roots', lambda _session, **kwargs: {})
    result = assets.get_show_asset_root_preview(
        session, source_id='episode:42', output_template='unsaved-template', local_media_profile_id=None,
    )
    assert received == [(show, 'unsaved-template')]
    assert result.path == '/library/Actual show'
    assert result.show_title == 'Actual show'
    assert result.system_enabled is True
    assert assets.get_show_asset_root_preview(
        session, source_id='example', output_template='unsaved-template', local_media_profile_id=None,
    ).path is None
    assert assets.get_show_asset_root_preview(
        session, source_id='episode:99', output_template='unsaved-template', local_media_profile_id=None,
    ).path is None


def test_preview_rejects_another_shows_root_but_allows_same_show_profiles(monkeypatch):
    monkeypatch.setattr(assets, 'get_settings', lambda: SimpleNamespace(
        download_settings=SimpleNamespace(download_show_assets=False),
    ))
    session = SimpleNamespace(get=lambda *_args: SimpleNamespace(show=SimpleNamespace(id=1, title='First')))
    monkeypatch.setattr(assets, 'resolve_show_media_directory', lambda *_args, **_kwargs: ShowMediaDirectory('/library/shared'))
    roots = {(1, 2): ShowMediaDirectory('/library/shared')}
    monkeypatch.setattr(assets, 'show_profile_roots', lambda *_args, **_kwargs: roots)
    arguments = dict(source_id='episode:42', output_template='draft', local_media_profile_id=2)
    assert assets.get_show_asset_root_preview(session, **arguments).path == '/library/shared'
    roots[2, 3] = ShowMediaDirectory('/library/shared')
    result = assets.get_show_asset_root_preview(session, **arguments)
    assert result.path is None
    assert 'another show' in result.reason
