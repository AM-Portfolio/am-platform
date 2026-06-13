import json
import logging
from typing import AsyncIterator
import httpx
from app.config import settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class LiteLLMProvider(BaseLLMProvider):
    """
    Routes all LLM calls through the internal LiteLLM proxy.
    LiteLLM handles model selection, API key management, retries,
    and forwards traces to Langfuse natively via its callback config.

    This is the recommended provider for production/preprod — it decouples
    the gateway from direct API key management.
    """

    def __init__(self):
        self.base_url = settings.LITELLM_BASE_URL.rstrip("/")
        self.api_key = settings.LITELLM_MASTER_KEY  # sk-... master key
        self.model = settings.LLM_MODEL             # e.g. "deepseek/deepseek-chat" or "gemini/gemini-2.0-flash"
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, prompt: str, system_prompt: str = None, stream: bool = False) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    async def generate_chat_stream(self, prompt: str, system_prompt: str = None) -> AsyncIterator[str]:
        """Stream response from LiteLLM proxy using OpenAI-compatible SSE."""
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(prompt, system_prompt, stream=True)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"LiteLLM stream error [{response.status_code}]: {error_body.decode()}")
                    response.raise_for_status()

                async for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        chunk = data["choices"][0]["delta"].get("content", "")
                        if chunk:
                            yield chunk
                    except Exception as e:
                        logger.error(f"Error parsing LiteLLM stream chunk: {e}")

    async def generate_chat(self, prompt: str, system_prompt: str = None) -> str:
        """Non-streaming call to LiteLLM proxy."""
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(prompt, system_prompt, stream=False)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            if response.status_code != 200:
                logger.error(f"LiteLLM error [{response.status_code}]: {response.text}")
                response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]
