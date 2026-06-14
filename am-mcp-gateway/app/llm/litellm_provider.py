import json
import logging
from typing import AsyncIterator, Union
import httpx
from app.config import settings
from app.llm.base import BaseLLMProvider
from app.llm.types import LLMChatResult, normalize_usage

logger = logging.getLogger(__name__)


class LiteLLMProvider(BaseLLMProvider):
    """
    Routes all LLM calls through the internal LiteLLM proxy.
    LiteLLM handles model selection, API key management, retries,
    and forwards traces to Langfuse natively via its callback config.
    """

    def __init__(self):
        self.base_url = settings.LITELLM_BASE_URL.rstrip("/")
        self.api_key = settings.LITELLM_MASTER_KEY
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self.last_usage = None

    def _headers(self) -> dict:
        if not self.api_key:
            raise ValueError("LITELLM_MASTER_KEY is not configured")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _resolve_model(self, model: str | None) -> str:
        return model or self.model

    def _resolve_temperature(self, temperature: float | None) -> float:
        return self.temperature if temperature is None else temperature

    def _payload(
        self,
        prompt: str,
        system_prompt: str | None,
        *,
        model: str | None,
        temperature: float | None,
        stream: bool,
        metadata: dict | None = None,
    ) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        resolved_model = self._resolve_model(model)
        body = {
            "model": resolved_model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature),
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if stream:
            body["stream_options"] = {"include_usage": True}
        if metadata:
            body["metadata"] = metadata
        return body

    def _raise_litellm_error(self, response: httpx.Response, *, model: str, stream: bool) -> None:
        body = response.text[:1000]
        detail = body
        try:
            detail = response.json().get("error", {}).get("message", body)
        except Exception:
            pass
        mode = "stream" if stream else "chat"
        raise RuntimeError(
            f"LiteLLM {mode} failed [{response.status_code}] model={model}: {detail}"
        )

    async def generate_chat_stream(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(
            prompt,
            system_prompt,
            model=model,
            temperature=temperature,
            stream=True,
            metadata=metadata,
        )
        resolved_model = payload["model"]
        self.last_usage = None
        logger.info("LiteLLM stream request model=%s url=%s", resolved_model, url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers=self._headers(),
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(
                        "LiteLLM stream error [%s] model=%s: %s",
                        response.status_code,
                        resolved_model,
                        error_body.decode()[:1000],
                    )
                    response._content = error_body
                    self._raise_litellm_error(response, model=resolved_model, stream=True)

                async for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        if data.get("usage"):
                            self.last_usage = normalize_usage(data["usage"])
                        chunk = data["choices"][0]["delta"].get("content", "")
                        if chunk:
                            yield chunk
                    except Exception as e:
                        logger.error(f"Error parsing LiteLLM stream chunk: {e}")

    async def generate_chat(
        self,
        prompt: str,
        system_prompt: str = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
    ) -> LLMChatResult:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(
            prompt,
            system_prompt,
            model=model,
            temperature=temperature,
            stream=False,
            metadata=metadata,
        )
        resolved_model = payload["model"]
        self.last_usage = None
        logger.info("LiteLLM chat request model=%s url=%s", resolved_model, url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            if response.status_code != 200:
                logger.error(
                    "LiteLLM error [%s] model=%s: %s",
                    response.status_code,
                    resolved_model,
                    response.text[:1000],
                )
                self._raise_litellm_error(response, model=resolved_model, stream=False)

            data = response.json()
            usage = normalize_usage(data.get("usage"))
            self.last_usage = usage
            text = data["choices"][0]["message"]["content"]
            return LLMChatResult(text=text, usage=usage, model=resolved_model)

    async def generate_chat_messages(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        metadata: dict | None = None,
        max_tokens: int | None = None,
    ) -> LLMChatResult:
        """Send a pre-built messages array (supports multimodal content)."""
        url = f"{self.base_url}/chat/completions"
        resolved_model = self._resolve_model(model)
        body: dict = {
            "model": resolved_model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature),
            "max_tokens": max_tokens or self.max_tokens,
            "stream": False,
        }
        if metadata:
            body["metadata"] = metadata
        self.last_usage = None
        logger.info("LiteLLM messages request model=%s url=%s", resolved_model, url)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self._headers(), json=body)
            if response.status_code != 200:
                logger.error(
                    "LiteLLM error [%s] model=%s: %s",
                    response.status_code,
                    resolved_model,
                    response.text[:1000],
                )
                self._raise_litellm_error(response, model=resolved_model, stream=False)

            data = response.json()
            usage = normalize_usage(data.get("usage"))
            self.last_usage = usage
            text = data["choices"][0]["message"]["content"]
            return LLMChatResult(text=text, usage=usage, model=resolved_model)
