"""Azure Cosmos DB state manager for Clinical Contexts.

Uses the NoSQL API with ``patient_id`` as the partition key for
efficient point-reads and cross-partition queries.
"""

from __future__ import annotations

from typing import Any

import structlog
from azure.cosmos.aio import CosmosClient, ContainerProxy
from azure.cosmos import PartitionKey, exceptions

from mednexus.config import settings
from mednexus.models.clinical_context import ClinicalContext, PatientDemographics

logger = structlog.get_logger()


class CosmosStateManager:
    """CRUD operations for ClinicalContext documents in Cosmos DB."""

    def __init__(self) -> None:
        self._client: CosmosClient | None = None
        self._container: ContainerProxy | None = None

    async def _ensure_container(self) -> ContainerProxy:
        """Lazy-initialise the Cosmos client and container."""
        if self._container is not None:
            return self._container

        self._client = CosmosClient(settings.cosmos_endpoint, settings.cosmos_key)
        db = await self._client.create_database_if_not_exists(settings.cosmos_database)
        self._container = await db.create_container_if_not_exists(
            id=settings.cosmos_container,
            partition_key=PartitionKey(path="/patient_id"),
        )
        logger.info(
            "cosmos_connected",
            database=settings.cosmos_database,
            container=settings.cosmos_container,
        )
        return self._container

    # ── CRUD ─────────────────────────────────────────────────

    async def get_context(self, patient_id: str) -> ClinicalContext | None:
        """Retrieve a Clinical Context by patient_id (point-read).

        Automatically migrates legacy flat-finding documents into
        the episode-based structure on first read.
        """
        container = await self._ensure_container()
        try:
            doc = await container.read_item(item=patient_id, partition_key=patient_id)
            ctx = ClinicalContext.from_cosmos_doc(doc)
            # Auto-migrate legacy flat contexts → episode-based
            if not ctx.episodes and (ctx.findings or ctx.ingested_files):
                ctx.migrate_legacy_to_episode()
                await self.upsert_context(ctx)
            return ctx
        except exceptions.CosmosResourceNotFoundError:
            return None

    async def upsert_context(self, ctx: ClinicalContext) -> ClinicalContext:
        """Create or update a Clinical Context in Cosmos DB."""
        container = await self._ensure_container()
        # Ensure Cosmos identifiers are set
        ctx.id = ctx.patient.patient_id
        ctx.partition_key = ctx.patient.patient_id
        ctx.touch()
        doc = ctx.to_cosmos_doc()
        # Top-level patient_id required as Cosmos partition key (/patient_id)
        doc["patient_id"] = ctx.patient.patient_id
        await container.upsert_item(doc)
        logger.info("cosmos_upserted", patient_id=ctx.patient.patient_id, status=ctx.status.value)
        return ctx

    async def create_context(self, patient_id: str, name: str = "") -> ClinicalContext:
        """Create a fresh Clinical Context for a new patient."""
        ctx = ClinicalContext(
            id=patient_id,
            partition_key=patient_id,
            patient=PatientDemographics(patient_id=patient_id, name=name),
        )
        return await self.upsert_context(ctx)

    async def list_contexts(self, limit: int = 50) -> list[ClinicalContext]:
        """Return the most recent Clinical Contexts (cross-partition query)."""
        container = await self._ensure_container()
        query = "SELECT * FROM c ORDER BY c.updated_at DESC OFFSET 0 LIMIT @limit"
        items: list[ClinicalContext] = []
        async for doc in container.query_items(
            query=query,
            parameters=[{"name": "@limit", "value": limit}],
        ):
            items.append(ClinicalContext.from_cosmos_doc(doc))
        return items

    async def delete_context(self, patient_id: str) -> bool:
        """Delete a Clinical Context."""
        container = await self._ensure_container()
        try:
            await container.delete_item(item=patient_id, partition_key=patient_id)
            return True
        except exceptions.CosmosResourceNotFoundError:
            return False

    # ── My Story ─────────────────────────────────────────────

    async def get_my_story(self, patient_id: str) -> dict | None:
        """Retrieve a patient's My Story document (point-read)."""
        container = await self._ensure_container()
        doc_id = f"{patient_id}__mystory"
        try:
            return await container.read_item(item=doc_id, partition_key=patient_id)
        except exceptions.CosmosResourceNotFoundError:
            return None

    async def save_my_story(self, patient_id: str, story: dict) -> dict:
        """Create or update a patient's My Story document."""
        container = await self._ensure_container()
        doc = {
            "id": f"{patient_id}__mystory",
            "patient_id": patient_id,
            "doc_type": "my_story",
            **story,
        }
        await container.upsert_item(doc)
        logger.info("my_story_saved", patient_id=patient_id)
        return doc

    # ── Cleanup ──────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.close()


# ── Singleton ────────────────────────────────────────────────
_instance: CosmosStateManager | None = None


def get_cosmos_manager() -> CosmosStateManager:
    global _instance
    if _instance is None:
        _instance = CosmosStateManager()
    return _instance
