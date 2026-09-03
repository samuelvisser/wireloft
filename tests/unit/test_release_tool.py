from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_TOOL_PATH = REPOSITORY_ROOT / "release.py"
SPEC = importlib.util.spec_from_file_location("wireloft_release_tool", RELEASE_TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
release_tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_tool
SPEC.loader.exec_module(release_tool)


def test_semantic_version_bumps():
    assert release_tool.bump_version("1.2.3", "major") == "2.0.0"
    assert release_tool.bump_version("1.2.3", "minor") == "1.3.0"
    assert release_tool.bump_version("1.2.3", "patch") == "1.2.4"


def test_distribution_names_are_normalized_for_package_tags():
    assert release_tool.normalize_distribution_name("DailyWire_API") == "dailywire-api"
    component = release_tool.Component(
        name="DailyWire_API",
        version="1.2.3",
        manifest=Path("server/example/pyproject.toml"),
        path=Path("server/example"),
    )
    assert component.tag == "dailywire-api-v1.2.3"


def test_project_version_replacement_only_changes_project_table():
    original = (
        '[tool.example]\nversion = "9.9.9"\n\n'
        '[project]\nname = "example"\nversion = "0.1.0"\n'
    )

    updated = release_tool.replace_project_version(original, "1.0.0")

    assert '[tool.example]\nversion = "9.9.9"' in updated
    assert '[project]\nname = "example"\nversion = "1.0.0"' in updated


def test_module_version_replacement_preserves_quote_style():
    assert release_tool.replace_module_version(
        "__version__ = '0.1.0'\n",
        "2.0.0",
    ) == "__version__ = '2.0.0'\n"


def test_release_container_tags_include_semver_aliases_and_latest():
    assert release_tool.container_tags("2.3.4") == ["2.3.4", "2.3", "2", "latest"]


def test_application_release_tag_is_pushed_separately(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run(*args: str, **_kwargs):
        calls.append(args)

    monkeypatch.setattr(release_tool, "run", fake_run)

    release_tool.push_release_tags(
        ["backend-v0.2.0", "config-v0.1.1"],
        "v1.1.0",
    )

    assert calls == [
        (
            "git",
            "push",
            "--atomic",
            "origin",
            "backend-v0.2.0",
            "config-v0.1.1",
        ),
        ("git", "push", "origin", "v1.1.0"),
    ]
