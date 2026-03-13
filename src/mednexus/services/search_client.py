"""Azure AI Search client for RAG retrieval.

Supports hybrid search (keyword + vector) across the clinical index:
  - Clinical text (structured PDFs, doctor notes)
  - X-ray analysis descriptions (Vision Specialist output)
  - Audio transcripts (Whisper → Patient Historian)

Embedding generation uses Azure OpenAI text-embedding-3-small (1536 dims).
"""

from __future__ import annotations

from typing import Any

import structlog
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery

from mednexus.config import settings

logger = structlog.get_logger()


# ── Auth helpers ───────────────────────────────────────────


def _search_configured() -> bool:
    return bool(settings.azure_search_endpoint) and (
        bool(settings.azure_search_key) or settings.use_managed_identity
    )


def _search_credential():
    if settings.use_managed_identity:
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential(
            managed_identity_client_id=settings.managed_identity_client_id
        )
    return AzureKeyCredential(settings.azure_search_key)


# ── Embedding helper ─────────────────────────────────────────


async def generate_embedding(text: str) -> list[float]:
    """Generate a vector embedding using Azure OpenAI.

    Returns a list of floats (1536 dimensions for text-embedding-3-small).
    """
    if not settings.azure_openai_endpoint or (
        not settings.azure_openai_api_key and not settings.use_managed_identity
    ):
        logger.warning("openai_not_configured_for_embeddings")
        return []

    from openai import AsyncAzureOpenAI
    from mednexus.services.llm_client import _azure_ad_token_provider

    if settings.use_managed_identity:
        client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_ad_token_provider=_azure_ad_token_provider(),
            api_version="2024-06-01",
            timeout=30.0,
            max_retries=1,
        )
    else:
        client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version="2024-06-01",
            timeout=30.0,
            max_retries=1,
        )
    response = await client.embeddings.create(
        input=text,
        model=settings.azure_openai_embedding_deployment,
    )
    return response.data[0].embedding


# ── Search functions ─────────────────────────────────────────


async def search_documents(
    query: str,
    *,
    filter_expr: str = "",
    top: int = 10,
    select: list[str] | None = None,
    use_vector: bool = True,
) -> list[dict[str, Any]]:
    """Hybrid search the MedNexus clinical index (keyword + vector).

    Parameters
    ----------
    query : str
        Free-text or semantic query.
    filter_expr : str
        OData filter, e.g. ``"patient_id eq 'P12345'"``
    top : int
        Maximum results to return.
    select : list[str] | None
        Fields to include in results.
    use_vector : bool
        If True (default), also performs vector search alongside keyword.

    Returns
    -------
    list[dict]
        List of matched documents with scores.
    """
    if not _search_configured():
        logger.warning("search_not_configured")
        return []

    async with SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=_search_credential(),
    ) as client:
        kwargs: dict[str, Any] = {
            "search_text": query,
            "top": top,
        }
        if filter_expr:
            kwargs["filter"] = filter_expr
        if select:
            kwargs["select"] = select

        # Vector component of hybrid search
        if use_vector:
            query_embedding = await generate_embedding(query)
            if query_embedding:
                kwargs["vector_queries"] = [
                    VectorizedQuery(
                        vector=query_embedding,
                        k_nearest_neighbors=top,
                        fields="content_vector",
                    ),
                ]

        results: list[dict[str, Any]] = []
        async for doc in await client.search(**kwargs):
            results.append(dict(doc))

        logger.info(
            "search_complete",
            query=query[:80],
            results=len(results),
            hybrid=use_vector and "vector_queries" in kwargs,
        )
        return results


async def search_patient_documents(
    patient_id: str,
    query: str,
    *,
    top: int = 10,
) -> list[dict[str, Any]]:
    """Convenience: hybrid search scoped to a single patient."""
    return await search_documents(
        query,
        filter_expr=f"patient_id eq '{patient_id}'",
        top=top,
        select=["id", "patient_id", "content_type", "content", "analysis_summary", "source_agent"],
    )


# ── Deletion functions ───────────────────────────────────────


async def delete_patient_documents(patient_id: str) -> int:
    """Delete all search documents for a patient. Returns count deleted."""
    if not _search_configured():
        return 0

    async with SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=_search_credential(),
    ) as client:
        # Collect all document IDs for this patient
        doc_ids: list[str] = []
        async for doc in await client.search(
            search_text="*",
            filter=f"patient_id eq '{patient_id}'",
            select=["id"],
            top=1000,
        ):
            doc_ids.append(doc["id"])

        if not doc_ids:
            return 0

        batch = [{"@search.action": "delete", "id": did} for did in doc_ids]
        await client.upload_documents(documents=batch)
        logger.info("search_documents_deleted", patient_id=patient_id, count=len(doc_ids))
        return len(doc_ids)


async def delete_documents_by_uris(uris: list[str]) -> int:
    """Delete search documents whose metadata_storage_path matches any of the given URIs.

    Because ``metadata_storage_path`` may not be marked filterable in the index
    schema, we search by patient_id (extracted from the URI) and then match the
    ``metadata_storage_path`` value in Python.
    """
    if not uris or not _search_configured():
        return 0

    # Extract patient IDs from az:// URIs (format: az://container/patientId_filename)
    patient_ids: set[str] = set()
    uri_set = set(uris)
    for uri in uris:
        parts = uri.split("/")
        if len(parts) >= 4:
            fname = parts[-1]
            pid = fname.split("_")[0] if "_" in fname else ""
            if pid:
                patient_ids.add(pid)

    async with SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=_search_credential(),
    ) as client:
        doc_ids: list[str] = []
        for pid in patient_ids:
            async for doc in await client.search(
                search_text="*",
                filter=f"patient_id eq '{pid}'",
                select=["id", "metadata_storage_path"],
                top=1000,
            ):
                if doc.get("metadata_storage_path") in uri_set:
                    doc_ids.append(doc["id"])

        if not doc_ids:
            return 0

        batch = [{"@search.action": "delete", "id": did} for did in doc_ids]
        await client.upload_documents(documents=batch)
        logger.info("search_documents_deleted_by_uri", count=len(doc_ids))
        return len(doc_ids)


# ── Indexing functions ───────────────────────────────────────


async def index_document(
    document: dict[str, Any],
    *,
    auto_embed: bool = True,
) -> None:
    """Index (upsert) a single document into the clinical search index.

    Expected fields: id, patient_id, content, content_type, source_agent, timestamp.

    If ``auto_embed`` is True and ``content_vector`` is not already in the
    document, an embedding will be generated from the ``content`` field.
    """
    if not _search_configured():
        logger.warning("search_not_configured_for_indexing")
        return

    # Auto-generate embedding if not provided
    if auto_embed and "content_vector" not in document:
        text = document.get("content", "") or document.get("analysis_summary", "")
        if text:
            document["content_vector"] = await generate_embedding(text)

    async with SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=_search_credential(),
    ) as client:
        await client.upload_documents(documents=[document])
        logger.info("document_indexed", doc_id=document.get("id"))


async def index_my_story(patient_id: str, story: dict[str, Any]) -> None:
    """Index a patient's My Story into AI Search for RAG retrieval."""
    import re

    safe_id = re.sub(r"[^a-zA-Z0-9_=\-]", "_", patient_id)
    content_parts = []
    if story.get("preferred_name"):
        content_parts.append(f"Patient prefers to be called {story['preferred_name']}.")
    if story.get("brings_joy"):
        content_parts.append(f"What brings joy: {story['brings_joy']}")
    if story.get("care_team_needs_to_know"):
        content_parts.append(f"Care team should know: {story['care_team_needs_to_know']}")
    if story.get("brings_peace"):
        content_parts.append(f"What brings peace: {story['brings_peace']}")

    content = " ".join(content_parts)
    if not content:
        return

    await index_document({
        "id": f"{safe_id}-my_story",
        "patient_id": patient_id,
        "content_type": "my_story",
        "content": content,
        "analysis_summary": f"Patient personal story: {content[:200]}",
        "source_agent": "doctor_input",
        "timestamp": story.get("recorded_at", ""),
    })
