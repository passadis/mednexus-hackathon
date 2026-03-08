"""Factory for creating the appropriate MCP server instance.

Reads the environment to decide: local filesystem vs. Azure Blob.
This ensures agents never hard-code file paths.
"""

from __future__ import annotations

from mednexus.config import settings
from mednexus.mcp.azure_blob import AzureBlobMCP
from mednexus.mcp.base import MCPServer
from mednexus.mcp.local_fs import LocalFileSystemMCP


def create_mcp_server() -> MCPServer:
    """Instantiate the right MCP backend based on config.

    * If ``AZURE_STORAGE_CONNECTION_STRING`` is set → use Azure Blob.
    * Otherwise → fall back to the local drop-folder.
    """
    if settings.azure_storage_connection_string:
        return AzureBlobMCP(
            connection_string=settings.azure_storage_connection_string,
            container_name=settings.azure_storage_container,
        )
    return LocalFileSystemMCP(root_dir=settings.mcp_drop_folder)
