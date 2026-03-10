"""Azure OpenAI / AI Foundry LLM client with multimodal support."""

from __future__ import annotations

from typing import Any

import structlog
from openai import AsyncAzureOpenAI

from mednexus.config import settings

logger = structlog.get_logger()


class LLMClient:
    """Thin async wrapper around Azure OpenAI for chat & vision completions."""

    def __init__(self) -> None:
        if settings.use_managed_identity:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential(
                managed_identity_client_id=settings.managed_identity_client_id
            )
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=settings.azure_openai_api_version,
            )
        else:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
            )
        self._deployment = settings.azure_openai_deployment

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        """Standard text chat completion."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def chat_with_image(
        self,
        system_prompt: str,
        user_prompt: str,
        image_b64: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """Multimodal chat completion (GPT-4o Vision)."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        resp = await self._client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def close(self) -> None:
        await self._client.close()


# ── Singleton ────────────────────────────────────────────────
_instance: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _instance
    if _instance is None:
        _instance = LLMClient()
    return _instance
