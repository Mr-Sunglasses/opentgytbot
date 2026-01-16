import re
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation using pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    telegram_bot_token: str = Field(default="", description="Telegram bot token from @BotFather")
    download_dir: str = Field(default="downloads", description="Directory for temporary downloads")
    max_concurrent_downloads: int = Field(
        default=5, ge=1, le=20, description="Maximum concurrent download workers"
    )
    max_video_size_mb: int = Field(
        default=50, ge=1, le=50, description="Maximum video size in MB (Telegram limit is 50MB)"
    )
    rate_limit_per_user: int = Field(
        default=10, ge=1, le=60, description="Maximum requests per user per minute"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper_v

    @field_validator("telegram_bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        # Basic Telegram bot token format validation
        if not re.match(r"^\d+:[A-Za-z0-9_-]+$", v):
            raise ValueError("Invalid Telegram bot token format")
        return v


# Initialize settings - will raise validation errors early
settings = Settings()

# Export as module-level constants for backward compatibility
TELEGRAM_BOT_TOKEN: Final = settings.telegram_bot_token
DOWNLOAD_DIR: Final = settings.download_dir
MAX_CONCURRENT_DOWNLOADS: Final = settings.max_concurrent_downloads
MAX_VIDEO_SIZE_MB: Final = settings.max_video_size_mb
RATE_LIMIT_PER_USER: Final = settings.rate_limit_per_user
LOG_LEVEL: Final = settings.log_level
