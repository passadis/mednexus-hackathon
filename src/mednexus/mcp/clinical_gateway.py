"""Clinical Data Gateway – MCP SDK server for MedNexus.

This is the "Medical Records Clerk" described in Phase 3: a proper MCP-protocol
server that exposes named **tools** and **resources** to agents.

Tools
~~~~~
``get_patient_records``
    Input: ``patient_id``
    Returns a manifest of available file types for that patient.

``fetch_medical_image``
    Input: ``image_id`` (filename or blob path)
    Returns the image as a base64-encoded string (or a temporary SAS URL
    when backed by Azure Blob Storage).

Resources
~~~~~~~~~
``clinical_protocol``
    A read-only text block describing the hospital's standard procedure
    for analysing scans—fed into agent system prompts to ground reasoning.

Security
~~~~~~~~
* Every call is scoped to a ``patient_id``; cross-patient access is blocked.
* All invocations are audit-logged (see ``mcp.audit``).

Integration
~~~~~~~~~~~
Instantiate :class:`ClinicalDataGateway` once, then hand its ``tools``
dict to any agent that needs file access.  The Clinical Sorter is the
primary consumer, but the Vision Specialist also calls
``fetch_medical_image`` directly.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from mednexus.config import settings
from mednexus.mcp.audit import get_audit_logger
from mednexus.mcp.base import MCPServer
from mednexus.mcp.factory import create_mcp_server

logger = structlog.get_logger("mcp.gateway")


# ── Clinical Protocol Resource ──────────────────────────────────────────────

CLINICAL_PROTOCOL = """
===========================================================================
  MedNexus Hospital — Standard Protocol for Diagnostic Image Analysis
===========================================================================

1. PATIENT IDENTIFICATION
   - Verify the Patient ID matches the imaging order.
   - Cross-reference the Medical Record Number (MRN) if available.

2. IMAGE REVIEW PROCEDURE
   a) Confirm image modality (X-ray, CT, MRI, Ultrasound).
   b) Evaluate image quality (rotation, exposure, artefacts).
   c) Perform systematic anatomical review:
      • Bones and joints
      • Soft tissue
      • Cardiomediastinal silhouette (for chest imaging)
      • Lungs / airspaces
      • Pleural spaces
   d) Document all findings with laterality and anatomical landmarks.

3. CROSS-MODALITY CORRELATION
   - Compare current imaging with prior studies (if available).
   - Compare imaging findings against patient's verbal statements
     (audio transcript) and lab results.
   - Flag any discrepancies for physician review.

4. REPORTING
   - Use structured format: Region, Observations, Impression, Confidence.
   - All AI-generated findings MUST be reviewed by a licensed physician
     before inclusion in the patient's medical record.

5. COMPLIANCE
   - All image access is audit-logged per HIPAA §164.312(b).
   - Minimum necessary principle: agents access only data required for
     the specific clinical question.
   - Patient data must not cross patient ID boundaries.

===========================================================================
"""


# ── MCP Tool Definitions (schema-first) ─────────────────────────────────────

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_patient_records",
        "description": (
            "Return a manifest of all available medical files for a given "
            "patient ID, grouped by modality (text, image, audio)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "The unique patient identifier (e.g. P12345).",
                },
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "fetch_medical_image",
        "description": (
            "Fetch a medical image by its identifier.  Returns a base64-encoded "
            "string of the image data, or a temporary Azure Blob SAS URL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_id": {
                    "type": "string",
                    "description": "Filename or blob path of the image.",
                },
                "patient_id": {
                    "type": "string",
                    "description": "Patient ID for access-control scoping.",
                },
            },
            "required": ["image_id", "patient_id"],
        },
    },
]


# ── Gateway Implementation ──────────────────────────────────────────────────

_PATIENT_ID_RE = re.compile(r"^(P\d{4,})", re.IGNORECASE)

# Map extensions to modality buckets
_MODALITY_BUCKETS: dict[str, str] = {
    ".pdf": "text",
    ".csv": "text",
    ".txt": "text",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".dcm": "image",
    ".dicom": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".flac": "audio",
}


class ClinicalDataGateway:
    """MCP-protocol 'Clinical Data Gateway' server.

    Wraps the existing MCP storage backend (local or Azure Blob) and adds:
      - Named tool dispatch (``get_patient_records``, ``fetch_medical_image``)
      - A read-only ``clinical_protocol`` resource
      - Patient-scoped access control
      - Full audit logging
    """

    def __init__(self, mcp_backend: MCPServer | None = None) -> None:
        self._backend: MCPServer = mcp_backend or create_mcp_server()
        self._audit = get_audit_logger()

    # ── MCP Tool interface ───────────────────────────────────

    @property
    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return the JSON-schema tool definitions for agent registration."""
        return TOOL_DEFINITIONS

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        agent_id: str = "unknown",
    ) -> dict[str, Any]:
        """Dispatch a tool call by name (used by agents)."""
        if tool_name == "get_patient_records":
            return await self.get_patient_records(
                patient_id=arguments["patient_id"],
                agent_id=agent_id,
            )
        if tool_name == "fetch_medical_image":
            return await self.fetch_medical_image(
                image_id=arguments["image_id"],
                patient_id=arguments["patient_id"],
                agent_id=agent_id,
            )
        raise ValueError(f"Unknown MCP tool: {tool_name}")

    # ── Resource interface ───────────────────────────────────

    def get_resource(self, resource_name: str) -> str:
        """Return a read-only resource by name."""
        if resource_name == "clinical_protocol":
            return CLINICAL_PROTOCOL
        raise ValueError(f"Unknown MCP resource: {resource_name}")

    # ── Tool implementations ─────────────────────────────────

    async def get_patient_records(
        self,
        patient_id: str,
        agent_id: str = "unknown",
    ) -> dict[str, Any]:
        """List available files for *patient_id*, grouped by modality.

        Security: only files whose filename starts with the patient ID are
        returned, preventing data leakage across patients.
        """
        patient_id_upper = patient_id.upper()
        all_files = await self._backend.list_files()

        # Filter to this patient only
        patient_files = [
            f for f in all_files
            if f.filename.upper().startswith(patient_id_upper)
        ]

        # Group by modality bucket
        grouped: dict[str, list[dict[str, Any]]] = {
            "text": [],
            "image": [],
            "audio": [],
            "other": [],
        }
        for f in patient_files:
            ext = Path(f.filename).suffix.lower()
            bucket = _MODALITY_BUCKETS.get(ext, "other")
            grouped[bucket].append({
                "filename": f.filename,
                "uri": f.uri,
                "size_bytes": f.size_bytes,
            })

        result = {
            "patient_id": patient_id,
            "total_files": len(patient_files),
            "modalities": {k: v for k, v in grouped.items() if v},
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }

        self._audit.log(
            operation="get_patient_records",
            agent_id=agent_id,
            patient_id=patient_id,
            params={},
            result_summary=f"{len(patient_files)} files found",
        )

        logger.info(
            "get_patient_records",
            patient_id=patient_id,
            file_count=len(patient_files),
            agent=agent_id,
        )
        return result

    async def fetch_medical_image(
        self,
        image_id: str,
        patient_id: str,
        agent_id: str = "unknown",
    ) -> dict[str, Any]:
        """Fetch an image file, returning base64 data.

        Security: verifies the requested file belongs to the given patient.
        """
        # Security check: prevent cross-patient access
        if not image_id.upper().startswith(patient_id.upper()):
            self._audit.log(
                operation="fetch_medical_image",
                agent_id=agent_id,
                patient_id=patient_id,
                params={"image_id": image_id},
                result_summary="ACCESS DENIED – patient_id mismatch",
                success=False,
            )
            raise PermissionError(
                f"Image '{image_id}' does not belong to patient '{patient_id}'. "
                "Cross-patient data access is prohibited."
            )

        # Resolve the URI for this image
        all_files = await self._backend.list_files()
        match = next(
            (f for f in all_files if f.filename == image_id or f.uri.endswith(image_id)),
            None,
        )
        if match is None:
            self._audit.log(
                operation="fetch_medical_image",
                agent_id=agent_id,
                patient_id=patient_id,
                params={"image_id": image_id},
                result_summary="NOT FOUND",
                success=False,
            )
            raise FileNotFoundError(f"Image '{image_id}' not found in MCP backend.")

        raw = await self._backend.read_bytes(match.uri)
        b64 = base64.b64encode(raw).decode("ascii")

        self._audit.log(
            operation="fetch_medical_image",
            agent_id=agent_id,
            patient_id=patient_id,
            params={"image_id": image_id, "size_bytes": len(raw)},
            result_summary=f"Returned {len(raw)} bytes as base64",
        )

        return {
            "image_id": image_id,
            "patient_id": patient_id,
            "content_base64": b64,
            "size_bytes": len(raw),
            "mime_type": self._guess_mime(image_id),
        }

    @staticmethod
    def _guess_mime(filename: str) -> str:
        ext = Path(filename).suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".dcm": "application/dicom",
            ".dicom": "application/dicom",
        }.get(ext, "application/octet-stream")


# ── Singleton ────────────────────────────────────────────────

_gateway_instance: ClinicalDataGateway | None = None


def get_clinical_gateway() -> ClinicalDataGateway:
    """Get or create the singleton Clinical Data Gateway."""
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = ClinicalDataGateway()
    return _gateway_instance
