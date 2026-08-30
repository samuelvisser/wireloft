from os import getenv
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import SettingsConfigDict, BaseSettings

from dailywire_api.config import PROJECT_ROOT


def get_config_path() -> Path:
    """Return the single YAML configuration file used by WireLoft."""
    return Path(
        getenv("WL_CONFIG_FILE", str(PROJECT_ROOT / "config" / "config.yml"))
    ).expanduser()


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
    """Normalize settings source keys to the model's camelCase aliases.

    pydantic-settings merges source dictionaries before model validation. An
    environment source uses Python field names (``log_level``), while YAML
    commonly uses aliases (``logLevel``). Without normalization both keys can
    survive the merge and Pydantic may then prefer an alias from a lower
    priority source. Canonical keys make source order authoritative.
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
        populate_by_name=True,
        env_prefix="WL_",
        env_nested_delimiter="__",
        env_file=getenv("WL_ENV_FILE", PROJECT_ROOT / ".env"),
        yaml_file=get_config_path(),
        extra="ignore",
        nested_model_default_partial_update=True,
    )
