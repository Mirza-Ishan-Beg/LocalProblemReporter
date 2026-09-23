"""Groq provider (OpenAI-compatible REST)."""

import os
import requests

from .base import LLMProvider


class GroqProvider(LLMProvider):
    name = "groq"

    ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
    MODEL    = "openai/gpt-oss-120b"
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com/keys"
            )

    def chat(self, messages: list[dict]) -> str:
        resp = requests.post(
            self.ENDPOINT,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       self.MODEL,
                "messages":    messages,
                "temperature": 0.3,
                "max_tokens":  512,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
