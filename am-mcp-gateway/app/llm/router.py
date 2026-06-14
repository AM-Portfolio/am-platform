import logging
from typing import AsyncIterator, Tuple

from app.llm.base import BaseLLMProvider
from app.llm.circuit_breaker import CircuitBreaker
from app.llm.factory import LLMProviderFactory
from app.llm.types import LLMChatResult

logger = logging.getLogger(__name__)


def _provider_key(provider: BaseLLMProvider) -> str:
    name = provider.__class__.__name__
    if name == "LiteLLMProvider":
        return "litellm"
    return name.replace("Provider", "").lower()


class LLMRouter:
    def __init__(self):
        self.providers_chain = LLMProviderFactory.get_fallback_chain()
        self.breakers = {
            "litellm":   CircuitBreaker("litellm"),
            "deepseek":  CircuitBreaker("deepseek"),
            "gemini":    CircuitBreaker("gemini"),
            "openai":    CircuitBreaker("openai"),
        }
        self.last_usage: dict[str, int] | None = None

    async def generate_chat_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> AsyncIterator[Tuple[str, str]]:
        last_error = None
        skipped: list[str] = []
        self.last_usage = None

        if not self.providers_chain:
            raise RuntimeError(
                "No LLM providers configured. Check LLM_FALLBACK_CHAIN and provider API keys."
            )

        for provider in self.providers_chain:
            provider_name = _provider_key(provider)
            breaker = self.breakers.get(provider_name)

            if breaker and not breaker.allow_request():
                logger.warning(f"Circuit breaker for {provider_name} is OPEN. Skipping...")
                skipped.append(f"{provider_name} (circuit OPEN)")
                continue

            logger.info(f"Attempting to stream chat via provider: {provider_name}")
            try:
                async for chunk in provider.generate_chat_stream(
                    prompt,
                    system_prompt,
                    model=model,
                    temperature=temperature,
                    metadata=metadata,
                ):
                    yield chunk, provider_name

                self.last_usage = getattr(provider, "last_usage", None)
                if breaker:
                    breaker.record_success()
                return
            except Exception as e:
                logger.error(f"Streaming failed with provider {provider_name}: {e}")
                last_error = e
                if breaker:
                    breaker.record_failure()

        if last_error:
            raise last_error
        if skipped:
            raise RuntimeError(
                f"All LLM providers unavailable: {', '.join(skipped)}. "
                "Restart the gateway or wait for circuit breaker recovery."
            )
        raise RuntimeError("All LLM providers skipped by circuit breakers or failed to initialize.")

    async def generate_chat(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> Tuple[str, str, dict[str, int] | None]:
        last_error = None
        skipped: list[str] = []
        self.last_usage = None

        if not self.providers_chain:
            raise RuntimeError(
                "No LLM providers configured. Check LLM_FALLBACK_CHAIN and provider API keys."
            )

        for provider in self.providers_chain:
            provider_name = _provider_key(provider)
            breaker = self.breakers.get(provider_name)

            if breaker and not breaker.allow_request():
                logger.warning(f"Circuit breaker for {provider_name} is OPEN. Skipping...")
                skipped.append(f"{provider_name} (circuit OPEN)")
                continue

            logger.info(f"Attempting chat via provider: {provider_name}")
            try:
                result = await provider.generate_chat(
                    prompt,
                    system_prompt,
                    model=model,
                    temperature=temperature,
                    metadata=metadata,
                )
                if isinstance(result, LLMChatResult):
                    self.last_usage = result.usage
                    text = result.text
                else:
                    self.last_usage = getattr(provider, "last_usage", None)
                    text = result

                if breaker:
                    breaker.record_success()
                return text, provider_name, self.last_usage
            except Exception as e:
                logger.error(f"Chat execution failed with provider {provider_name}: {e}")
                last_error = e
                if breaker:
                    breaker.record_failure()

        if last_error:
            raise last_error
        if skipped:
            raise RuntimeError(
                f"All LLM providers unavailable: {', '.join(skipped)}. "
                "Restart the gateway or wait for circuit breaker recovery."
            )
        raise RuntimeError("All LLM providers skipped by circuit breakers or failed to initialize.")

    async def generate_chat_messages(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
        max_tokens: int | None = None,
    ) -> Tuple[str, str, dict[str, int] | None]:
        """Route a raw messages payload (multimodal) through the LiteLLM provider chain."""
        last_error = None
        skipped: list[str] = []
        self.last_usage = None

        for provider in self.providers_chain:
            provider_name = _provider_key(provider)
            if provider_name != "litellm":
                continue
            breaker = self.breakers.get(provider_name)
            if breaker and not breaker.allow_request():
                skipped.append(f"{provider_name} (circuit OPEN)")
                continue
            try:
                result = await provider.generate_chat_messages(
                    messages,
                    model=model,
                    temperature=temperature,
                    metadata=metadata,
                    max_tokens=max_tokens,
                )
                self.last_usage = result.usage
                if breaker:
                    breaker.record_success()
                return result.text, provider_name, self.last_usage
            except Exception as e:
                last_error = e
                if breaker:
                    breaker.record_failure()

        if last_error:
            raise last_error
        raise RuntimeError(
            "Multimodal LLM requests require LiteLLM provider. "
            f"Skipped/unavailable: {', '.join(skipped) or 'none configured'}"
        )


llm_router = LLMRouter()
