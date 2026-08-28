from os import getenv

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import SettingsConfigDict, BaseSettings

from dailywire_api.config import PROJECT_ROOT


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
        # Let a source (config.yml, in practice -- see settings.py) specify only
        # some fields of a nested settings block (e.g. just downloadRoot) and
        # have the rest fall back to that block's own defaults, instead of
        # requiring every field once any one of them is set. Pydantic-settings
        # only applies this to a field's *default* though, not a default_factory
        # -- see the comment on AppSettings' nested fields.
        nested_model_default_partial_update=True,
    )