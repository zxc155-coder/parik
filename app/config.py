from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., description="Telegram bot token from @BotFather")
    canopywave_api_key: str = Field(..., description="Canopy Wave API key")
    canopywave_base_url: str = Field(
        default="https://api.canopywave.io/v1",
        description="Base URL of the Canopy Wave OpenAI-compatible endpoint",
    )
    text_model: str = Field(default="minimax/minimax-m2.5")
    vision_model: str = Field(default="zai/glm-5.1")

    # Optional separate provider for vision (e.g. OpenRouter). If unset, the same
    # canopywave_api_key + canopywave_base_url are used.
    vision_api_key: str = Field(default="")
    vision_base_url: str = Field(default="")

    webapp_url: str = Field(default="", description="Public HTTPS URL of the Web App")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    allowed_user_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to use the bot. Empty = public.",
    )

    @property
    def allowed_ids(self) -> set[int]:
        if not self.allowed_user_ids.strip():
            return set()
        return {int(x.strip()) for x in self.allowed_user_ids.split(",") if x.strip()}


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
