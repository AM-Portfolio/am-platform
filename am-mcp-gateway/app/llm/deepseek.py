import json
import logging
from typing import AsyncIterator
import httpx
from app.config import settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

class DeepSeekProvider(BaseLLMProvider):
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.LLM_MODEL or "deepseek-chat"
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    async def generate_chat_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"DeepSeek stream error response: {error_text.decode()}")
                    response.raise_for_status()

                async for line in response.iter_lines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            chunk = data["choices"][0]["delta"].get("content", "")
                            if chunk:
                                yield chunk
                        except Exception as e:
                            logger.error(f"Error parsing DeepSeek stream chunk: {e}")

    async def generate_chat(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> str:
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.error(f"DeepSeek response error: {response.text}")
                response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
