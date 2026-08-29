from config.config import PROJECT_ROOT
from config.settings.settings import AppSettings


def test_default_database_path_uses_config_directory():
    assert AppSettings.model_fields["database_path"].default == PROJECT_ROOT / "config" / "wireloft.db"
