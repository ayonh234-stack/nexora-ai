"""OpenAI-compatible chat client (xAI, Gemini, or OpenAI)."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from openai import OpenAI

from sglbot.config import Config
from sglbot.prompts import SAVE_LEAD_TOOL

logger = logging.getLogger(__name__)

ToolHandler = Callable[[str, dict[str, Any]], str]

_RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "unavailable",
    "high demand",
    "rate limit",
    "timeout",
    "timed out",
    "overloaded",
    "try again",
)
_TOOLS_UNSUPPORTED_MARKERS = (
    "tool",
    "function call",
    "function_call",
    "unknown field",
    "not supported",
    "unsupported",
    "invalid argument",
    "does not support",
)


# Strongest free Gemini models first; each falls back to the next on 429/503/404/timeouts,
# and the configured model (flash-lite by default) is always the last resort.
SMART_GEMINI_MODELS = ("gemini-3-flash-preview", "gemini-3.5-flash")
_FALLBACK_MARKERS = _RETRYABLE_MARKERS + ("404", "not found", "no longer available", "quota", "resource_exhausted", "permission")
_cooldown: dict[str, float] = {}


def model_chain(cfg) -> list[str]:
    env = (os.getenv("AI_MODELS") or "").strip()
    if env:
        chain = [m.strip() for m in env.split(",") if m.strip()]
    elif str(cfg.ai_model).startswith("gemini"):
        chain = [*SMART_GEMINI_MODELS, cfg.ai_model]
    else:
        chain = [cfg.ai_model]
    seen: list[str] = []
    for m in chain:
        if m not in seen:
            seen.append(m)
    now = time.time()
    usable = [m for m in seen[:-1] if _cooldown.get(m, 0) < now] + seen[-1:]
    return usable


def mark_failed(model: str, exc: BaseException) -> None:
    text = _err_text(exc)
    secs = 900 if ("quota" in text or "429" in text or "404" in text or "no longer" in text) else 180
    _cooldown[model] = time.time() + secs
    logger.warning("Model %s unavailable (%s); cooling down %ss", model, type(exc).__name__, secs)


def should_fallback(exc: BaseException) -> bool:
    text = _err_text(exc)
    return any(m in text for m in _FALLBACK_MARKERS)


def fast_client(client: OpenAI, last: bool) -> OpenAI:
    """Non-final models fail fast so the fallback model can still answer in time."""
    return client if last else client.with_options(timeout=30.0, max_retries=0)


def build_client(cfg: Config) -> OpenAI:
    if cfg.ai_base_url:
        return OpenAI(api_key=cfg.ai_api_key, base_url=cfg.ai_base_url, timeout=60.0)
    return OpenAI(api_key=cfg.ai_api_key, timeout=60.0)


def _err_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}".lower()


def _is_retryable(exc: BaseException) -> bool:
    text = _err_text(exc)
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def _is_tools_unsupported(exc: BaseException) -> bool:
    text = _err_text(exc)
    return any(marker in text for marker in _TOOLS_UNSUPPORTED_MARKERS)


def complete(
    client: OpenAI,
    cfg: Config,
    *,
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
    tools: list[dict] | None = None,
    on_tool: ToolHandler | None = None,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    tools_enabled = bool(tools) and on_tool is not None
    last_message_content = ""
    chain = model_chain(cfg)
    model_i = 0

    for round_i in range(3):
        kwargs: dict[str, Any] = {
            "model": chain[model_i],
            "messages": messages,
            "temperature": 0.7,
        }
        if tools_enabled:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = None
        for attempt in range(3 + len(chain)):
            kwargs["model"] = chain[model_i]
            last_model = model_i == len(chain) - 1
            try:
                response = fast_client(client, last_model).chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if not last_model and round_i == 0 and should_fallback(exc):
                    mark_failed(chain[model_i], exc)
                    model_i += 1
                    continue
                if tools_enabled and _is_tools_unsupported(exc):
                    logger.warning(
                        "Tool calling not accepted by %s (%s); retrying without tools",
                        kwargs["model"],
                        type(exc).__name__,
                    )
                    tools_enabled = False
                    kwargs.pop("tools", None)
                    kwargs.pop("tool_choice", None)
                    continue
                if _is_retryable(exc) and attempt < 2 + len(chain):
                    delay = 1.5 * (attempt + 1)
                    logger.warning(
                        "AI request failed (%s); retrying in %.1fs",
                        type(exc).__name__,
                        delay,
                    )
                    time.sleep(delay)
                    continue
                raise

        if response is None:
            continue

        choice = response.choices[0]
        message = choice.message
        last_message_content = (message.content or "").strip()
        tool_calls = getattr(message, "tool_calls", None) or []

        if not tool_calls or not tools_enabled or on_tool is None:
            if last_message_content:
                return last_message_content
            # Empty text with no tool calls — don't keep looping forever.
            return last_message_content

        messages.append(
            {
                "role": "assistant",
                "content": message.content or None,
                # Keep provider extras (Gemini 3 needs extra_content.google.thought_signature
                # echoed back, otherwise the follow-up request fails with HTTP 400).
                "tool_calls": [_tool_call_dict(call) for call in tool_calls],
            }
        )
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                logger.warning(
                    "Invalid tool arguments for %s: %s", name, call.function.arguments
                )
                args = {}
            result = on_tool(name, args)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )

    return last_message_content


def _tool_call_dict(call: Any) -> dict[str, Any]:
    try:
        data = call.model_dump(exclude_none=True)
    except Exception:
        data = {}
    data.setdefault("id", call.id)
    data["type"] = "function"
    data["function"] = {
        "name": call.function.name,
        "arguments": call.function.arguments or "{}",
    }
    return data


def growth_tools() -> list[dict]:
    return [SAVE_LEAD_TOOL]
