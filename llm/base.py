"""Provider-agnostic LLM interface."""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Every provider must implement .chat(messages) -> str."""

    name: str = "base"

    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """
        messages: list of {"role": "system"|"user"|"assistant",
                           "content": "..."}
        returns:  plain assistant reply string
        """
        raise NotImplementedError
