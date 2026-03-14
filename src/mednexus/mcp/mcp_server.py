"""Real MCP-protocol server backed by the Clinical Data Gateway.

Uses the ``mcp`` Python SDK (FastMCP) to expose the same tools and resources
that agents already consume in-process, but over the standard MCP transport
(Streamable HTTP / JSON-RPC 2.0).

Mount the Starlette app returned by :func:`get_mcp_app` inside the main
FastAPI application::

    app.mount("/mcp", get_mcp_app())

Nothing in the existing agent code changes — this is a purely additive
protocol facade over :class:`~mednexus.mcp.clinical_gateway.ClinicalDataGateway`.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from mednexus.mcp.clinical_gateway import get_clinical_gateway

# ── FastMCP instance ─────────────────────────────────────────────────────────

mcp_server = FastMCP(
    "MedNexus Clinical Gateway",
    instructions=(
        "MedNexus Clinical Data Gateway — provides patient-scoped access to "
        "medical records (text, images, audio) with HIPAA-compliant audit "
        "logging.  Use get_patient_records to discover available files, and "
        "fetch_medical_image to retrieve imaging data."
    ),
)


# ── Tools (delegate to the existing gateway singleton) ───────────────────────


@mcp_server.tool(
    name="get_patient_records",
    description=(
        "Return a manifest of all available medical files for a given "
        "patient ID, grouped by modality (text, image, audio)."
    ),
)
async def get_patient_records(patient_id: str) -> str:
    """List available files for a patient, grouped by modality."""
    gw = get_clinical_gateway()
    result = await gw.call_tool(
        "get_patient_records",
        {"patient_id": patient_id},
        agent_id="mcp-client",
    )
    return json.dumps(result, default=str)


@mcp_server.tool(
    name="fetch_medical_image",
    description=(
        "Fetch a medical image by its identifier.  Returns a base64-encoded "
        "string of the image data, or a temporary Azure Blob SAS URL."
    ),
)
async def fetch_medical_image(image_id: str, patient_id: str) -> str:
    """Fetch a medical image with patient-scoped access control."""
    gw = get_clinical_gateway()
    result = await gw.call_tool(
        "fetch_medical_image",
        {"image_id": image_id, "patient_id": patient_id},
        agent_id="mcp-client",
    )
    return json.dumps(result, default=str)


# ── Resources ────────────────────────────────────────────────────────────────


@mcp_server.resource(
    "clinical://protocol",
    name="clinical_protocol",
    description=(
        "MedNexus Hospital standard protocol for diagnostic image analysis. "
        "Read-only reference document used to ground agent reasoning."
    ),
)
def clinical_protocol() -> str:
    """Return the hospital's standard analysis protocol."""
    gw = get_clinical_gateway()
    return gw.get_resource("clinical_protocol")


# ── App factory ──────────────────────────────────────────────────────────────


def get_mcp_app() -> Any:
    """Return a Starlette ASGI app serving the MCP protocol over Streamable HTTP."""
    return mcp_server.streamable_http_app()
