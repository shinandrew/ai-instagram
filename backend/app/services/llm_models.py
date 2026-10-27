"""
Central OpenAI model configuration.

gpt-4o / gpt-4o-mini are retired on 2027-01-14; OpenAI's recommended replacement
for both is gpt-6-luna. GPT-5+ models reject `max_tokens` (use
`max_completion_tokens`) and only accept the default temperature, so call sites
build their sampling arguments through `chat_params()`.

Override per deployment with OPENAI_TEXT_MODEL / OPENAI_VISION_MODEL /
OPENAI_REASONING_EFFORT.
"""
import os

TEXT_MODEL = os.environ.get("OPENAI_TEXT_MODEL", "gpt-6-luna")
VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-6-luna")
REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "none")

_LEGACY_PREFIXES = ("gpt-4", "gpt-3.5")


def chat_params(model: str, *, max_tokens: int | None = None, temperature: float | None = None) -> dict:
    """Keyword arguments for chat.completions.create() that the given model accepts."""
    params: dict = {"model": model}
    if model.startswith(_LEGACY_PREFIXES):
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if temperature is not None:
            params["temperature"] = temperature
    else:
        if max_tokens is not None:
            params["max_completion_tokens"] = max_tokens
        if REASONING_EFFORT:
            params["reasoning_effort"] = REASONING_EFFORT
    return params
