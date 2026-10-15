from typing import List

try:
    import tomllib  # Python 3.11+ standard library
except ImportError:
    import tomli as tomllib
from pydantic import BaseModel, field_validator, ConfigDict


class Site(BaseModel):
    name: str
    url: str

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value):
        if not value:
            raise ValueError("site name can not be empty")
        return value

    @field_validator("url")
    @classmethod
    def url_has_scheme(cls, value):
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class Settings(BaseModel):
    title: str = "linkwatch"
    output: str = "status.html"
    sites: List[Site] = []

    model_config = ConfigDict(extra="forbid")


def load_settings(path="sites.toml"):
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return Settings(**data)
