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


# ── Embedding helper ─────────────────────────────────────────


async def generate_embedding(text: str) -> list[float]:
    """Generate a vector embedding using Azure OpenAI.

    Returns a list of floats (1536 dimensions for text-embedding-3-small).
    """
    if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        logger.warning("openai_not_configured_for_embeddings")
        return []

    from openai import AsyncAzureOpenAI

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version="2024-06-01",
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
    if not settings.azure_search_endpoint or not settings.azure_search_key:
        logger.warning("search_not_configured")
        return []

    async with SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=AzureKeyCredential(settings.azure_search_key),
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
    if not settings.azure_search_endpoint or not settings.azure_search_key:
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
        credential=AzureKeyCredential(settings.azure_search_key),
    ) as client:
        await client.upload_documents(documents=[document])
        logger.info("document_indexed", doc_id=document.get("id"))
