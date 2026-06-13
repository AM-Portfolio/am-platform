from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_chat_stream(self, prompt: str, system_prompt: str = None) -> AsyncIterator[str]:
        """Generate streamed tokens from the LLM."""
        pass

    @abstractmethod
    async def generate_chat(self, prompt: str, system_prompt: str = None) -> str:
        """Generate full response from the LLM synchronously."""
        pass
