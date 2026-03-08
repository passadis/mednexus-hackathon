"""Clinical Sorter Agent – monitors the MCP drop-folder and classifies files.

This agent is the "intake desk" of MedNexus.  It:
  1. Watches the MCP server for new files.
  2. Classifies each file by type (image, PDF, audio, etc.).
  3. Extracts a patient_id (from filename convention or metadata).
  4. Notifies the Orchestrator to dispatch the file to the right specialist.

Phase 3: The Clinical Sorter is the **primary consumer** of the Clinical
Data Gateway MCP server tools (``get_patient_records``,
``fetch_medical_image``).
"""

from __future__ import annotations

import re
from typing import Any

from mednexus.agents.base import BaseAgent
from mednexus.models.agent_messages import AgentRole, TaskAssignment, TaskResult
from mednexus.models.medical_files import FileType, MedicalFile


# Filename convention: PATIENTID_description.ext  e.g. P12345_chest_xray.png
_PATIENT_ID_RE = re.compile(r"^(P\d{4,})", re.IGNORECASE)


class ClinicalSorterAgent(BaseAgent):
    """Watches the MCP file source and classifies incoming medical files.

    Uses the Clinical Data Gateway MCP tools for patient-scoped file
    discovery and secure image access.
    """

    role = AgentRole.CLINICAL_SORTER

    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Classify a single file (can also be called ad-hoc by orchestrator)."""
        filename = assignment.file_uri.split("/")[-1].split("\\")[-1]
        file_type = MedicalFile.classify(filename)
        patient_id = self._extract_patient_id(filename) or assignment.patient_id

        return TaskResult(
            task_id=assignment.task_id,
            patient_id=patient_id,
            agent=self.role,
            success=True,
            summary=f"Classified {filename} as {file_type.value}",
            structured_output={
                "filename": filename,
                "file_type": file_type.value,
                "patient_id": patient_id,
                "uri": assignment.file_uri,
            },
        )

    async def classify_file(self, filename: str, uri: str) -> MedicalFile:
        """Convenience: classify and return a MedicalFile model."""
        ftype = MedicalFile.classify(filename)
        pid = self._extract_patient_id(filename) or ""
        return MedicalFile(
            filename=filename,
            uri=uri,
            file_type=ftype,
            patient_id=pid,
        )

    # ── MCP Gateway integration (Phase 3) ───────────────────

    async def get_patient_records(self, patient_id: str) -> dict[str, Any]:
        """Use the MCP Clinical Data Gateway to list a patient's files.

        This is the primary way agents discover what data is available
        for a given patient.  All access is audit-logged.
        """
        from mednexus.mcp.clinical_gateway import get_clinical_gateway

        gw = get_clinical_gateway()
        return await gw.call_tool(
            "get_patient_records",
            {"patient_id": patient_id},
            agent_id=self.agent_id,
        )

    async def fetch_medical_image(self, image_id: str, patient_id: str) -> dict[str, Any]:
        """Use the MCP Clinical Data Gateway to securely fetch an image."""
        from mednexus.mcp.clinical_gateway import get_clinical_gateway

        gw = get_clinical_gateway()
        return await gw.call_tool(
            "fetch_medical_image",
            {"image_id": image_id, "patient_id": patient_id},
            agent_id=self.agent_id,
        )

    def get_clinical_protocol(self) -> str:
        """Retrieve the hospital's standard analysis protocol (read-only resource)."""
        from mednexus.mcp.clinical_gateway import get_clinical_gateway

        gw = get_clinical_gateway()
        return gw.get_resource("clinical_protocol")

    @staticmethod
    def _extract_patient_id(filename: str) -> str:
        """Try to pull a patient ID from the filename."""
        m = _PATIENT_ID_RE.match(filename)
        return m.group(1).upper() if m else ""
