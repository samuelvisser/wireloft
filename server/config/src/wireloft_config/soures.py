import json
import os
from typing import Optional, Any, Dict
from pathlib import Path

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, YamlConfigSettingsSource


class FileSettingsSource(YamlConfigSettingsSource):
    """Custom source that loads a config file pointed to by SETTINGS_FILE (env) or default path."""


