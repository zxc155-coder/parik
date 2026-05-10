"""Registry of AI text models a user can switch between.

Each entry pairs a model id (passed straight to the upstream OpenAI-compatible
API) with a logical provider key understood by ``CanopyWaveClient.chat`` and a
human-readable label / description that appears on the inline keyboard buttons
and inside the Telegram Web App model picker.

Only models that have been smoke-tested against the configured API keys are
listed; flaky free OpenRouter endpoints that frequently return 5xx are kept
out so the user doesn't see random failures when switching.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelChoice:
    id: str
    """Provider-specific model identifier (e.g. ``minimax/minimax-m2.5``)."""

    label: str
    """Short label shown on the inline keyboard / picker button."""

    provider: str
    """Logical provider name (``canopywave`` or ``openrouter``)."""

    description: str
    """One-line description shown in /model output and the Web App picker."""

    speed: str
    """Speed hint shown in the picker: ``fast``, ``medium``, ``slow``."""

    badge: str = ""
    """Short emoji/text pinned on the picker card (e.g. ``free``, ``vision``)."""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


# Order = display order. Each row in the inline keyboard, top-to-bottom.
# We curate a diverse mix: reasoning models (slow, smart), instant models
# (fast, terse), and balanced models. All tested against the active keys.
AVAILABLE_MODELS: tuple[ModelChoice, ...] = (
    ModelChoice(
        id="minimax/minimax-m2.5",
        label="🧠 MiniMax M2.5",
        provider="canopywave",
        description="Reasoning-модель Canopy Wave. Думает 7–13 сек, даёт глубокие развёрнутые ответы.",
        speed="slow",
        badge="reasoning",
    ),
    ModelChoice(
        id="xiaomimimo/mimo-v2-flash",
        label="⚡ MiMo V2 Flash",
        provider="canopywave",
        description="Лёгкая модель Canopy Wave. Отвечает за 1–3 сек, подходит для быстрых вопросов.",
        speed="fast",
    ),
    ModelChoice(
        id="xiaomimimo/mimo-v2.5",
        label="🎯 MiMo V2.5",
        provider="canopywave",
        description="Сбалансированная модель Canopy Wave. Разумно быстро и достаточно умно.",
        speed="medium",
    ),
    ModelChoice(
        id="openai/gpt-oss-20b:free",
        label="🚀 GPT-OSS 20B",
        provider="openrouter",
        description="Бесплатная маленькая модель OpenAI на OpenRouter. Самая быстрая в списке.",
        speed="fast",
        badge="free",
    ),
    ModelChoice(
        id="openai/gpt-oss-120b:free",
        label="🦾 GPT-OSS 120B",
        provider="openrouter",
        description="Большая бесплатная модель OpenAI на OpenRouter. Умнее 20B, тоже быстрая.",
        speed="fast",
        badge="free",
    ),
    ModelChoice(
        id="z-ai/glm-4.5-air:free",
        label="🌌 GLM 4.5 Air",
        provider="openrouter",
        description="Бесплатная reasoning-модель Z.ai. Хорошо рассуждает и пишет на русском.",
        speed="medium",
        badge="free",
    ),
    ModelChoice(
        id="google/gemma-4-26b-a4b-it:free",
        label="💎 Gemma 4 26B",
        provider="openrouter",
        description="Бесплатная модель Google Gemma 4. Сбалансирована и быстрая.",
        speed="fast",
        badge="free",
    ),
    ModelChoice(
        id="nvidia/nemotron-nano-9b-v2:free",
        label="💚 Nemotron Nano",
        provider="openrouter",
        description="Бесплатная reasoning-модель NVIDIA. Шустрая, неплохо отвечает на простые задачи.",
        speed="fast",
        badge="free",
    ),
)


_BY_ID = {m.id: m for m in AVAILABLE_MODELS}


def get_default() -> ModelChoice:
    return AVAILABLE_MODELS[0]


def get_by_id(model_id: str) -> ModelChoice | None:
    return _BY_ID.get(model_id)
