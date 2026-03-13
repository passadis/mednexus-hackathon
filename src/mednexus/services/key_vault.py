"""Optional Key Vault secret fallback for Container Apps deployments."""

from __future__ import annotations

import structlog
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from mednexus.config import settings

logger = structlog.get_logger()

_PLACEHOLDER_VALUES = {
    "",
    "mednexus-portal-secret-change-me",
}


def _get_secret_client() -> SecretClient | None:
    if not settings.azure_key_vault_url or not settings.use_managed_identity:
        return None

    credential = DefaultAzureCredential(
        managed_identity_client_id=settings.managed_identity_client_id or None
    )
    return SecretClient(vault_url=settings.azure_key_vault_url, credential=credential)


def _apply_secret_if_missing(
    client: SecretClient,
    *,
    current_value: str,
    attr_name: str,
    secret_name: str,
) -> None:
    if current_value not in _PLACEHOLDER_VALUES or not secret_name:
        return

    secret = client.get_secret(secret_name)
    setattr(settings, attr_name, secret.value or "")
    logger.info("key_vault_secret_loaded", setting=attr_name, secret_name=secret_name)


def load_key_vault_overrides() -> None:
    """Load secrets from Key Vault only when env vars were not already supplied."""
    client = _get_secret_client()
    if client is None:
        return

    try:
        _apply_secret_if_missing(
            client,
            current_value=settings.cosmos_key,
            attr_name="cosmos_key",
            secret_name=settings.cosmos_key_secret_name,
        )
        _apply_secret_if_missing(
            client,
            current_value=settings.portal_jwt_secret,
            attr_name="portal_jwt_secret",
            secret_name=settings.portal_jwt_secret_name,
        )
        _apply_secret_if_missing(
            client,
            current_value=settings.azure_openai_realtime_key,
            attr_name="azure_openai_realtime_key",
            secret_name=settings.azure_openai_realtime_key_secret_name,
        )
    except Exception:
        logger.warning("key_vault_secret_load_failed", exc_info=True)
