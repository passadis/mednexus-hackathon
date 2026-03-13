"""Azure OpenAI / AI Foundry LLM client with multimodal support."""

from __future__ import annotations

from typing import Any

import structlog
from openai import AsyncAzureOpenAI

from mednexus.config import settings
from mednexus.observability import mark_span_failure, start_span

logger = structlog.get_logger()


def _azure_ad_token_provider():
    from azure.identity import ManagedIdentityCredential, get_bearer_token_provider

    credential = ManagedIdentityCredential(
        client_id=settings.managed_identity_client_id or None
    )
    return get_bearer_token_provider(
        credential,
        "https://cognitiveservices.azure.com/.default",
    )


def create_openai_client() -> AsyncAzureOpenAI:
    """Build an Azure OpenAI client using MI when enabled."""
    if settings.use_managed_identity:
        return AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_ad_token_provider=_azure_ad_token_provider(),
            api_version=settings.azure_openai_api_version,
            timeout=30.0,
            max_retries=1,
        )

    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        timeout=30.0,
        max_retries=1,
    )


def create_agent_framework_chat_client():
    """Build a Microsoft Agent Framework Azure chat client."""
    from agent_framework.azure import AzureOpenAIChatClient

    return AzureOpenAIChatClient(
        async_client=create_openai_client(),
        deployment_name=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
    )


class LLMClient:
    """Thin async wrapper around Azure OpenAI for chat & vision completions."""

    def __init__(self) -> None:
        self._client = create_openai_client()
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

        with start_span(
            "llm.chat_completion",
            tracer_name="llm",
            attributes={
                "mednexus.ai.operation": "chat",
                "mednexus.ai.deployment": self._deployment,
                "mednexus.ai.temperature": temperature,
                "mednexus.ai.max_tokens": max_tokens,
                "mednexus.ai.response_format": bool(response_format),
            },
        ) as span:
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

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

        with start_span(
            "llm.vision_completion",
            tracer_name="llm",
            attributes={
                "mednexus.ai.operation": "vision",
                "mednexus.ai.deployment": self._deployment,
                "mednexus.ai.temperature": temperature,
                "mednexus.ai.max_tokens": max_tokens,
                "mednexus.ai.response_format": bool(response_format),
            },
        ) as span:
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

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
