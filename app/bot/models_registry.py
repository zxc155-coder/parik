"""Registry of AI text models a Telegram user can switch between via /model.

Each entry pairs a model id (passed straight to the upstream OpenAI-compatible
API) with a logical provider key understood by ``CanopyWaveClient.chat`` and a
human-readable label that appears on the inline keyboard buttons.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelChoice:
    id: str
    """Provider-specific model identifier (e.g. ``minimax/minimax-m2.5``)."""

    label: str
    """Short label shown on the inline keyboard."""

    provider: str
    """Logical provider name (``canopywave`` or ``openrouter``)."""

    description: str
    """One-line description shown in /model output."""


# Order matters: shown top-to-bottom in /model. Keep it tight; one button per row.
AVAILABLE_MODELS: tuple[ModelChoice, ...] = (
    ModelChoice(
        id="minimax/minimax-m2.5",
        label="🧠 MiniMax M2.5 (умная, медленная)",
        provider="canopywave",
        description="Reasoning-модель Canopy Wave. Думает дольше, но даёт глубокие ответы.",
    ),
    ModelChoice(
        id="xiaomimimo/mimo-v2-flash",
        label="⚡ MiMo V2 Flash (быстрая)",
        provider="canopywave",
        description="Лёгкая модель Canopy Wave, отвечает за 1-3 секунды.",
    ),
    ModelChoice(
        id="xiaomimimo/mimo-v2.5",
        label="🎯 MiMo V2.5 (баланс)",
        provider="canopywave",
        description="Сбалансированная модель Canopy Wave: разумно быстро и достаточно умно.",
    ),
    ModelChoice(
        id="openai/gpt-oss-20b:free",
        label="🚀 GPT-OSS 20B (мгновенная)",
        provider="openrouter",
        description="Бесплатная маленькая модель OpenRouter. Самая быстрая, простые ответы.",
    ),
)


_BY_ID = {m.id: m for m in AVAILABLE_MODELS}


def get_default() -> ModelChoice:
    return AVAILABLE_MODELS[0]


def get_by_id(model_id: str) -> ModelChoice | None:
    return _BY_ID.get(model_id)
