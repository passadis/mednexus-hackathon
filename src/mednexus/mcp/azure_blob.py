"""Azure Blob Storage MCP server – monitors a container for new blobs."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from mednexus.mcp.base import MCPFileEvent, MCPServer


class AzureBlobMCP(MCPServer):
    """MCP backend backed by an Azure Blob Storage container.

    Blobs that have been processed are moved to a ``processed/`` virtual
    directory within the same container.
    """

    def __init__(self, connection_string: str, container_name: str) -> None:
        self._conn_str = connection_string
        self._container = container_name
        self._seen: set[str] = set()

    def _get_client(self):  # noqa: ANN202
        from azure.storage.blob.aio import ContainerClient

        return ContainerClient.from_connection_string(self._conn_str, self._container)

    # ── interface ────────────────────────────────────────────

    async def list_files(self) -> list[MCPFileEvent]:
        events: list[MCPFileEvent] = []
        async with self._get_client() as client:
            async for blob in client.list_blobs():
                if not blob.name.startswith("processed/") and not blob.name.startswith("_"):
                    events.append(
                        MCPFileEvent(
                            filename=blob.name.split("/")[-1],
                            uri=f"az://{self._container}/{blob.name}",
                            size_bytes=blob.size or 0,
                        )
                    )
        return events

    async def watch(self, poll_seconds: float = 10.0) -> AsyncIterator[MCPFileEvent]:
        while True:
            async with self._get_client() as client:
                async for blob in client.list_blobs():
                    if blob.name.startswith("processed/") or blob.name.startswith("_"):
                        continue
                    key = f"{blob.name}:{blob.last_modified}"
                    if key not in self._seen:
                        self._seen.add(key)
                        yield MCPFileEvent(
                            filename=blob.name.split("/")[-1],
                            uri=f"az://{self._container}/{blob.name}",
                            size_bytes=blob.size or 0,
                        )
            await asyncio.sleep(poll_seconds)

    async def read_bytes(self, uri: str) -> bytes:
        # uri format: az://container/blobname
        blob_name = "/".join(uri.split("/")[3:])
        async with self._get_client() as client:
            blob = client.get_blob_client(blob_name)
            stream = await blob.download_blob()
            return await stream.readall()

    async def move_to_processed(self, uri: str) -> str:
        blob_name = "/".join(uri.split("/")[3:])
        dest_name = f"processed/{blob_name}"
        async with self._get_client() as client:
            src_blob = client.get_blob_client(blob_name)
            dst_blob = client.get_blob_client(dest_name)
            await dst_blob.start_copy_from_url(src_blob.url)
            await src_blob.delete_blob()
        return f"az://{self._container}/{dest_name}"

    async def healthcheck(self) -> bool:
        try:
            async with self._get_client() as client:
                await client.get_container_properties()
            return True
        except Exception:
            return False
