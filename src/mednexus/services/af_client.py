"""Microsoft Agent Framework – shared AzureOpenAIChatClient factory.

Provides a cached client instance used by all AF-powered agents
(Doctor Chat, orchestration workflow, specialist wrappers).
"""

from __future__ import annotations

import functools

from agent_framework.azure import AzureOpenAIChatClient

from mednexus.config import settings


@functools.cache
def get_af_client() -> AzureOpenAIChatClient:
    """Return a shared ``AzureOpenAIChatClient`` (created once, cached)."""
    if settings.use_managed_identity:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        credential = DefaultAzureCredential(
            managed_identity_client_id=settings.managed_identity_client_id
        )
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAIChatClient(
            endpoint=settings.azure_openai_endpoint,
            deployment_name=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
            credential=token_provider,
        )

    return AzureOpenAIChatClient(
        endpoint=settings.azure_openai_endpoint,
        deployment_name=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        api_key=settings.azure_openai_api_key,
    )
