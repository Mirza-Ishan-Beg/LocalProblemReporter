"""Provider factory."""

import os

from .base import LLMProvider
from .groq import GroqProvider
from .snowflake import SnowflakeProvider

_REGISTRY = {
    "groq":       GroqProvider,
    "snowflake":  SnowflakeProvider,
}

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider

    name = os.environ.get("LLM_PROVIDER", "groq").lower()
    cls = _REGISTRY.get(name)
    if cls is None:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{name}'. "
            f"Valid options: {list(_REGISTRY)}"
        )
    _provider = cls()
    return _provider
