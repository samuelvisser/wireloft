from os import getenv
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import SettingsConfigDict, BaseSettings

from dailywire_api.config import PROJECT_ROOT


def get_ui_config_path() -> Path:
    """Return the YAML file managed exclusively by the Settings UI.

    By default the file lives beside config.yml so both files are retained by
    the same persistent /config volume in container deployments. An explicit
    path can be supplied for unusual installations with WL_UI_CONFIG_FILE.
    """
    explicit_path = getenv("WL_UI_CONFIG_FILE")
    if explicit_path:
        return Path(explicit_path).expanduser()

    config_path = Path(
        getenv("WL_CONFIG_FILE", str(PROJECT_ROOT / "config" / "config.yml"))
    ).expanduser()
    return config_path.with_name("ui-settings.yml")


def _nested_settings_model(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation

    for argument in get_args(annotation):
        nested = _nested_settings_model(argument)
        if nested is not None:
            return nested
    return None


def normalize_settings_source_keys(
    data: dict[str, Any],
    model_type: type[BaseModel],
) -> dict[str, Any]:
    """Normalize every settings source to the model's camelCase aliases.

    pydantic-settings merges source dictionaries before model validation. An
    environment source uses Python field names (``log_level``), while YAML
    commonly uses aliases (``logLevel``). Without normalization both keys can
    survive the merge and Pydantic then prefers the alias regardless of source
    order, allowing a lower-priority YAML value to beat an environment value.
    Canonical keys make the declared source order authoritative.
    """
    fields_by_input_key: dict[str, tuple[str, Any]] = {}
    for field_name, field in model_type.model_fields.items():
        alias = field.alias or field_name
        fields_by_input_key[field_name] = (alias, field.annotation)
        fields_by_input_key[alias] = (alias, field.annotation)

    normalized: dict[str, Any] = {}
    for input_key, value in data.items():
        alias, annotation = fields_by_input_key.get(input_key, (input_key, None))
        nested_model = _nested_settings_model(annotation) if annotation is not None else None
        if nested_model is not None and isinstance(value, dict):
            value = normalize_settings_source_keys(value, nested_model)
        normalized[alias] = value
    return normalized


class SubmodelBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True
    )


class SettingsBase(BaseSettings):
    model_config = SettingsConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # <- accept either alias or field name on input
        env_prefix="WL_",
        env_nested_delimiter="__",
        env_file=getenv("WL_ENV_FILE", PROJECT_ROOT / ".env"),
        yaml_file=getenv("WL_CONFIG_FILE", PROJECT_ROOT / "config" / "config.yml"),
        extra="ignore",
        nested_model_default_partial_update=True,
    )
