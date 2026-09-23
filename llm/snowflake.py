"""Snowflake Cortex provider — placeholder for when you wire it in."""

from .base import LLMProvider


class SnowflakeProvider(LLMProvider):
    name = "snowflake"

    def __init__(self):
        raise NotImplementedError(
            "SnowflakeProvider is not implemented yet. "
            "Set LLM_PROVIDER=groq for now, or fill this in when ready."
        )

    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError
