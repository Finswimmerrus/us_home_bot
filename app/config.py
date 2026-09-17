from __future__ import annotations

from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    BOT_TOKEN: SecretStr = SecretStr("")
    DATABASE_URL: SecretStr = SecretStr(
        "postgresql+asyncpg://user:password@localhost:5432/couple_bot"
    )
    TEST_DATABASE_URL: SecretStr | None = None
    DEFAULT_TIMEZONE: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def validate_values(self) -> "Settings":
        try:
            ZoneInfo(self.DEFAULT_TIMEZONE)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid DEFAULT_TIMEZONE: {self.DEFAULT_TIMEZONE}") from exc
        level = self.LOG_LEVEL.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid LOG_LEVEL: {self.LOG_LEVEL}")
        object.__setattr__(self, "LOG_LEVEL", level)
        return self

    def validate_for_start(self) -> None:
        if not self.BOT_TOKEN.get_secret_value():
            raise ValueError("BOT_TOKEN is required")
        if not self.DATABASE_URL.get_secret_value():
            raise ValueError("DATABASE_URL is required")


settings = Settings()
config = SimpleNamespace(
    BOT_TOKEN=settings.BOT_TOKEN.get_secret_value(),
    DATABASE_URL=settings.DATABASE_URL.get_secret_value(),
    TEST_DATABASE_URL=(
        settings.TEST_DATABASE_URL.get_secret_value()
        if settings.TEST_DATABASE_URL
        else None
    ),
    DEFAULT_TIMEZONE=settings.DEFAULT_TIMEZONE,
    LOG_LEVEL=settings.LOG_LEVEL,
)


def get_settings() -> Settings:
    return settings
