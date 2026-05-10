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
    # canopywave_api_key + canopywave_base_url are used. ``vision_api_keys`` may be
    # comma-separated to enable round-robin / failover across multiple OpenRouter
    # keys — useful for working around the free-tier daily quota by spreading
    # calls across several accounts. ``vision_api_key`` (singular) is kept for
    # backwards compat and used when ``vision_api_keys`` is empty.
    vision_api_key: str = Field(default="")
    vision_api_keys: str = Field(default="")
    vision_base_url: str = Field(default="")

    # Inline mode uses a deliberately FAST model so we answer within Telegram's
    # ~10s inline_query timeout. By default we route inline through the same
    # vision provider (OpenRouter has good free fast models). Override per env.
    inline_model: str = Field(default="openai/gpt-oss-20b:free")
    inline_api_key: str = Field(default="")
    inline_base_url: str = Field(default="")
    inline_timeout: float = Field(default=8.0)

    webapp_url: str = Field(default="", description="Public HTTPS URL of the Web App")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Webhook mode (production hosting on Render/Heroku/etc.). When `webhook_base_url`
    # is set, the bot registers a webhook at <base>/webhook instead of long-polling.
    # Render's free plan spins down on inactivity from incoming HTTP requests, so
    # webhook mode (which causes Telegram to POST on every update) keeps it warm.
    webhook_base_url: str = Field(default="")
    webhook_path: str = Field(default="/webhook")
    webhook_secret: str = Field(default="")

    # Self-ping keep-alive: when running on a Render Free plan, the service spins
    # down after 15 min without inbound HTTP. A small background task here pings
    # `<keepalive_url>` every `keepalive_interval` seconds (recommended 600 = 10 min)
    # so the inbound traffic counter never resets. If `keepalive_url` is empty
    # but `webhook_base_url` is set, we fall back to <webhook_base_url>/api/health.
    keepalive_url: str = Field(default="")
    keepalive_interval: float = Field(default=600.0)

    allowed_user_ids: str = Field(
        default="",
        description="Comma-separated Telegram user IDs allowed to use the bot. Empty = public.",
    )

    @property
    def allowed_ids(self) -> set[int]:
        if not self.allowed_user_ids.strip():
            return set()
        return {int(x.strip()) for x in self.allowed_user_ids.split(",") if x.strip()}

    @property
    def openrouter_keys(self) -> list[str]:
        """All OpenRouter keys to round-robin over (vision_api_keys ∪ vision_api_key)."""
        keys: list[str] = []
        seen: set[str] = set()
        for raw in (self.vision_api_keys or "").split(","):
            k = raw.strip()
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
        single = (self.vision_api_key or "").strip()
        if single and single not in seen:
            seen.add(single)
            keys.append(single)
        return keys


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
