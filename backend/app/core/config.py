import os
from dataclasses import dataclass


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.environ.get(name, default).split(",") if item.strip())


def _boolean(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    allowed_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    enable_api_docs: bool

    @classmethod
    def from_environment(cls):
        environment = os.environ.get("APP_ENV", "development").strip().lower()
        return cls(
            environment=environment,
            allowed_origins=_csv("ALLOWED_ORIGINS"),
            allowed_hosts=_csv("ALLOWED_HOSTS", "*"),
            enable_api_docs=_boolean("ENABLE_API_DOCS", environment != "production"),
        )
