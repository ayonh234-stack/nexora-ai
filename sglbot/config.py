"""Environment configuration. Values are loaded lazily via load()."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"
GEMINI_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# Current xAI chat model (verified from https://docs.x.ai/developers/models,
# Nov 2026). grok-4.3 is the lower-cost current model; set AI_MODEL=grok-4.7
# for the flagship. Retired slugs such as grok-4-fast / grok-3-mini now redirect.
DEFAULT_XAI_MODEL = "grok-4.3"
# Current Gemini free-tier model verified against this project's API key
# (Nov 2026). gemini-2.5-flash is no longer available to new users;
# Google recommends gemini-3.8-flash, which often 503s on the free tier.
# gemini-3.5-flash-lite completed chat + tool calls reliably.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_MEMORY_TURNS = 20


class ConfigError(SystemExit):
    """Raised / used as a clean process exit when required config is missing."""


@dataclass(frozen=True)
class Config:
    telegram_token: str
    ai_api_key: str
    ai_base_url: str | None
    ai_model: str
    provider: str  # "xai", "gemini", or "openai"
    admin_chat_id: int | None
    data_dir: Path
    db_path: Path
    leads_csv_path: Path
    memory_turns: int
    log_level: str
    port: int | None


def _optional_int(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(
            f"{name} must be a numeric Telegram chat ID, got: {raw!r}"
        ) from exc


def load(*, require_telegram: bool = True, require_ai: bool = True) -> Config:
    """Load config from the environment (and an optional local .env file)."""
    load_dotenv()

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if require_telegram and not token:
        raise ConfigError(
            "Missing TELEGRAM_BOT_TOKEN. Copy .env.example to .env and add the "
            "token you received from Telegram @BotFather."
        )

    xai_key = (os.getenv("XAI_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model_override = (os.getenv("AI_MODEL") or "").strip() or None

    if xai_key:
        provider = "xai"
        ai_api_key = xai_key
        ai_base_url = (os.getenv("XAI_BASE_URL") or "").strip() or XAI_DEFAULT_BASE_URL
        ai_model = model_override or DEFAULT_XAI_MODEL
    elif gemini_key:
        provider = "gemini"
        ai_api_key = gemini_key
        ai_base_url = (os.getenv("GEMINI_BASE_URL") or "").strip() or GEMINI_DEFAULT_BASE_URL
        ai_model = model_override or DEFAULT_GEMINI_MODEL
    elif openai_key:
        provider = "openai"
        ai_api_key = openai_key
        ai_base_url = None
        ai_model = model_override or DEFAULT_OPENAI_MODEL
    else:
        provider = ""
        ai_api_key = ""
        ai_base_url = None
        ai_model = model_override or DEFAULT_GEMINI_MODEL
        if require_ai:
            raise ConfigError(
                "Missing AI key. Set XAI_API_KEY (preferred), GEMINI_API_KEY, "
                "or OPENAI_API_KEY in your .env file. Priority: xAI > Gemini > OpenAI."
            )

    data_dir = Path(os.getenv("DATA_DIR") or "data").expanduser()
    if not data_dir.is_absolute():
        data_dir = Path.cwd() / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    turns_raw = (os.getenv("MEMORY_TURNS") or str(DEFAULT_MEMORY_TURNS)).strip()
    try:
        memory_turns = max(2, int(turns_raw))
    except ValueError:
        memory_turns = DEFAULT_MEMORY_TURNS

    port_raw = (os.getenv("PORT") or "").strip()
    port = int(port_raw) if port_raw.isdigit() else None

    return Config(
        telegram_token=token,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        provider=provider or "unset",
        admin_chat_id=_optional_int("ADMIN_CHAT_ID"),
        data_dir=data_dir,
        db_path=data_dir / "memory.sqlite",
        leads_csv_path=data_dir / "leads.csv",
        memory_turns=memory_turns,
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        port=port,
    )
