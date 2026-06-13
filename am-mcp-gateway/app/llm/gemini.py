import json
import logging
from typing import AsyncIterator
import httpx
from app.config import settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.model = "gemini-1.5-flash"
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    async def generate_chat_stream(self, prompt: str, system_prompt: str = None) -> AsyncIterator[str]:
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}"

        contents = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Instruction: {system_prompt}"}]
            })
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Gemini stream error response: {error_text.decode()}")
                    response.raise_for_status()

                # Gemini streams a JSON array of responses, or Server-Sent Events sometimes.
                # Actually, streamGenerateContent returns a JSON array of objects or streaming chunks.
                # Let's read buffer and process chunks of JSON objects.
                buffer = ""
                async for chunk in response.iter_text():
                    buffer += chunk
                    # Try to parse individual objects from the streaming JSON array.
                    # It usually comes as `[ { ... }, { ... } ]`.
                    # We can do basic extraction of text.
                    # A robust way is to yield anything that looks like "text": "..."
                    # Or extract contents from json objects:
                    # Let's do simple cleaning or line/bracket based parsing:
                    while True:
                        buffer = buffer.strip()
                        if not buffer:
                            break
                        
                        # Strip starting array brackets if present
                        if buffer.startswith("["):
                            buffer = buffer[1:].strip()
                            continue
                        if buffer.startswith(","):
                            buffer = buffer[1:].strip()
                            continue
                        
                        # Find the first complete JSON object in the buffer
                        try:
                            # Let's parse JSON objects by finding matching braces
                            brace_count = 0
                            end_idx = -1
                            for idx, char in enumerate(buffer):
                                if char == "{":
                                    brace_count += 1
                                elif char == "}":
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_idx = idx + 1
                                        break
                            
                            if end_idx != -1:
                                obj_str = buffer[:end_idx]
                                buffer = buffer[end_idx:].strip()
                                
                                data = json.loads(obj_str)
                                text = data["candidates"][0]["content"]["parts"][0]["text"]
                                if text:
                                    yield text
                            else:
                                break # incomplete JSON object, wait for more data
                        except Exception as e:
                            # If parsing fails, it might be partial. Just wait.
                            break

    async def generate_chat(self, prompt: str, system_prompt: str = None) -> str:
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not configured")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Instruction: {system_prompt}"}]
            })
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                logger.error(f"Gemini response error: {response.text}")
                response.raise_for_status()
            
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
