"""Azure AI Search index bootstrap for MedNexus."""

from __future__ import annotations

import structlog
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from mednexus.config import settings

logger = structlog.get_logger()


def _credential():
    if settings.use_managed_identity:
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential(
            managed_identity_client_id=settings.managed_identity_client_id or None
        )
    return AzureKeyCredential(settings.azure_search_key)


def _index_enabled() -> bool:
    return bool(settings.azure_search_endpoint) and (
        bool(settings.azure_search_key) or settings.use_managed_identity
    )


async def ensure_search_index() -> None:
    """Create or update the MedNexus search index when configured."""
    if not settings.mednexus_bootstrap_search_index or not _index_enabled():
        return

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(
            name="patient_id",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="content_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SimpleField(
            name="source_agent",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
            analyzer_name="en.microsoft",
        ),
        SearchableField(
            name="analysis_summary",
            type=SearchFieldDataType.String,
            analyzer_name="en.microsoft",
        ),
        SimpleField(
            name="metadata_storage_path",
            type=SearchFieldDataType.String,
            filterable=False,
        ),
        SimpleField(
            name="timestamp",
            type=SearchFieldDataType.DateTimeOffset,
            filterable=True,
            sortable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=settings.azure_openai_embedding_dimensions,
            vector_search_profile_name="mednexus-vector-profile",
        ),
    ]

    index = SearchIndex(
        name=settings.azure_search_index,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[
                HnswAlgorithmConfiguration(
                    name="mednexus-hnsw",
                    parameters=HnswParameters(
                        m=4,
                        ef_construction=400,
                        ef_search=500,
                        metric="cosine",
                    ),
                )
            ],
            profiles=[
                VectorSearchProfile(
                    name="mednexus-vector-profile",
                    algorithm_configuration_name="mednexus-hnsw",
                ),
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="mednexus-semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="analysis_summary"),
                        content_fields=[SemanticField(field_name="content")],
                        keywords_fields=[SemanticField(field_name="content_type")],
                    ),
                ),
            ],
        ),
    )

    async with SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=_credential(),
    ) as client:
        try:
            await client.create_or_update_index(index)
            logger.info("search_index_ready", index=settings.azure_search_index)
        except HttpResponseError as exc:
            error_code = getattr(exc, "error", None)
            code = getattr(error_code, "code", "") if error_code else ""
            message = str(exc)
            if code in {"OperationNotAllowed", "CannotChangeExistingField"} or "cannot be changed" in message.lower():
                logger.warning(
                    "search_index_existing_schema_preserved",
                    index=settings.azure_search_index,
                    error_code=code or "OperationNotAllowed",
                )
                return
            raise
