import logging
from typing import AsyncIterator, Tuple
from app.llm.base import BaseLLMProvider
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.factory import LLMProviderFactory

logger = logging.getLogger(__name__)

class LLMRouter:
    def __init__(self):
        self.providers_chain = LLMProviderFactory.get_fallback_chain()
        self.breakers = {
            "litellm":   CircuitBreaker("litellm"),
            "deepseek":  CircuitBreaker("deepseek"),
            "gemini":    CircuitBreaker("gemini"),
            "openai":    CircuitBreaker("openai"),
        }

    async def generate_chat_stream(self, prompt: str, system_prompt: str = None) -> AsyncIterator[Tuple[str, str]]:
        """
        Attempts to stream chat responses, falling back to alternative providers
        if the current one fails or is blocked by its circuit breaker.
        Yields tuples of (text_chunk, provider_name).
        """
        last_error = None
        
        for provider in self.providers_chain:
            provider_name = provider.__class__.__name__.replace("Provider", "").lower()
            breaker = self.breakers.get(provider_name)

            if breaker and not breaker.allow_request():
                logger.warning(f"Circuit breaker for {provider_name} is OPEN. Skipping...")
                continue

            logger.info(f"Attempting to stream chat via provider: {provider_name}")
            try:
                # To be able to record success/failure, we consume the generator and yield chunks
                chunks = []
                async for chunk in provider.generate_chat_stream(prompt, system_prompt):
                    chunks.append(chunk)
                    yield chunk, provider_name
                
                # If we made it here without error, record success
                if breaker:
                    breaker.record_success()
                return # Successfully processed stream
            except Exception as e:
                logger.error(f"Streaming failed with provider {provider_name}: {e}")
                last_error = e
                if breaker:
                    breaker.record_failure()
                # Continue loop to try next provider in chain

        if last_error:
            raise last_error
        else:
            raise RuntimeError("All LLM providers skipped by circuit breakers or failed to initialize.")

    async def generate_chat(self, prompt: str, system_prompt: str = None) -> Tuple[str, str]:
        """
        Attempts to generate a full chat response synchronously, falling back to alternative
        providers if the current one fails or is blocked by its circuit breaker.
        Returns (response_text, provider_name).
        """
        last_error = None

        for provider in self.providers_chain:
            provider_name = provider.__class__.__name__.replace("Provider", "").lower()
            breaker = self.breakers.get(provider_name)

            if breaker and not breaker.allow_request():
                logger.warning(f"Circuit breaker for {provider_name} is OPEN. Skipping...")
                continue

            logger.info(f"Attempting chat via provider: {provider_name}")
            try:
                response = await provider.generate_chat(prompt, system_prompt)
                if breaker:
                    breaker.record_success()
                return response, provider_name
            except Exception as e:
                logger.error(f"Chat execution failed with provider {provider_name}: {e}")
                last_error = e
                if breaker:
                    breaker.record_failure()
                # Continue loop to try next provider in chain

        if last_error:
            raise last_error
        else:
            raise RuntimeError("All LLM providers skipped by circuit breakers or failed to initialize.")

llm_router = LLMRouter()
