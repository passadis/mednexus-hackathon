"""Centralised configuration loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings sourced from env vars / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Azure OpenAI ─────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_embedding_dimensions: int = 1536
    azure_openai_whisper_deployment: str = "whisper"

    # ── Azure OpenAI Realtime (Voice) ───────────────────────
    azure_openai_realtime_endpoint: str = ""
    azure_openai_realtime_key: str = ""
    azure_openai_realtime_deployment: str = "gpt-realtime"

    # ── Azure AI Vision ──────────────────────────────────────
    azure_ai_vision_endpoint: str = ""
    azure_ai_vision_key: str = ""

    # ── Azure AI Search ──────────────────────────────────────
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "mednexus-clinical"

    # ── Azure Cosmos DB ──────────────────────────────────────
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "mednexus"
    cosmos_container: str = "clinical_contexts"

    # ── Azure Blob Storage ───────────────────────────────────
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "mednexus-intake"

    # ── Azure Speech ─────────────────────────────────────────
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"

    # ── Portal JWT ────────────────────────────────────────────
    portal_jwt_secret: str = "mednexus-portal-secret-change-me"
    portal_jwt_expiry_hours: int = 48

    # ── Application ──────────────────────────────────────────
    mednexus_log_level: str = "INFO"
    mednexus_cors_origins: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:80"
    )
    mcp_drop_folder: str = "./data/intake"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated origins.

        A wildcard ``*`` can be used when running behind a Dapr sidecar
        (the nginx frontend already proxies via Dapr so all requests
        arrive as same-origin from the sidecar).  For Container Apps set
        ``MEDNEXUS_CORS_ORIGINS`` to the frontend FQDN or ``*``.
        """
        raw = [o.strip() for o in self.mednexus_cors_origins.split(",") if o.strip()]
        return raw


# Singleton – import this everywhere
settings = Settings()
