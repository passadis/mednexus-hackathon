"""MCP Server layer – abstracted file source for clinical document intake.

The MCP design lets us hot-swap the data source (local disk ↔ Azure Blob)
without any agent code changes.

Phase 3 adds the **Clinical Data Gateway** — a proper MCP-protocol server
implementing named tools (``get_patient_records``, ``fetch_medical_image``)
and a read-only ``clinical_protocol`` resource, with full audit logging.
"""

from mednexus.mcp.base import MCPServer
from mednexus.mcp.local_fs import LocalFileSystemMCP
from mednexus.mcp.azure_blob import AzureBlobMCP
from mednexus.mcp.factory import create_mcp_server
from mednexus.mcp.clinical_gateway import ClinicalDataGateway, get_clinical_gateway
from mednexus.mcp.audit import MCPAuditLogger, get_audit_logger

__all__ = ["AzureBlobMCP", "LocalFileSystemMCP", "MCPServer", "create_mcp_server"]
