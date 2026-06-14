import logging
from typing import Dict, List
from app.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.deepseek import DeepSeekProvider
from app.llm.gemini import GeminiProvider
from app.llm.openai import OpenAIProvider
from app.llm.litellm_provider import LiteLLMProvider

logger = logging.getLogger(__name__)

class LLMProviderFactory:
    _providers: Dict[str, BaseLLMProvider] = {}

    @classmethod
    def get_provider(cls, name: str) -> BaseLLMProvider:
        name_lower = name.lower().strip()
        if name_lower not in cls._providers:
            if name_lower == "deepseek":
                cls._providers[name_lower] = DeepSeekProvider()
            elif name_lower == "gemini":
                cls._providers[name_lower] = GeminiProvider()
            elif name_lower == "openai":
                cls._providers[name_lower] = OpenAIProvider()
            elif name_lower == "litellm":
                cls._providers[name_lower] = LiteLLMProvider()
            else:
                raise ValueError(f"Unknown LLM provider: {name}")
        return cls._providers[name_lower]

    @classmethod
    def get_fallback_chain(cls) -> List[BaseLLMProvider]:
        chain = []
        for provider_name in settings.fallback_chain_list:
            try:
                chain.append(cls.get_provider(provider_name))
            except Exception as e:
                logger.error(f"Failed to initialize LLM provider '{provider_name}': {e}")
        return chain
