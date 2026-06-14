from abc import ABC, abstractmethod
from typing import AsyncIterator, Union

from app.llm.types import LLMChatResult


class BaseLLMProvider(ABC):
    last_usage: dict[str, int] | None = None

    @abstractmethod
    async def generate_chat_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> AsyncIterator[str]:
        """Generate streamed tokens from the LLM."""
        pass

    @abstractmethod
    async def generate_chat(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> Union[str, LLMChatResult]:
        """Generate full response from the LLM synchronously."""
        pass
