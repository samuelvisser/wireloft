import tomllib

from config.config import PROJECT_ROOT
from config.settings.settings import AppSettings, get_app_version


def test_default_database_path_uses_config_directory():
    assert AppSettings.model_fields["database_path"].default == PROJECT_ROOT / "config" / "wireloft.db"


def test_default_app_version_comes_from_root_project_version():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
        project_version = tomllib.load(file)["project"]["version"]

    assert get_app_version() == project_version
    assert AppSettings.model_fields["app_version"].default_factory() == project_version
