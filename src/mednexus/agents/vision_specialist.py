"""Vision Specialist Agent – analyses medical images via Azure AI Vision + GPT-4o.

Pipeline:
  1. Receive an image file URI from the Orchestrator.
  2. Read raw bytes via the MCP layer.
  3. Send to Azure AI Vision for low-level feature extraction.
  4. Send image + features to GPT-4o (multimodal) for clinical interpretation.
  5. Return structured radiology-style finding.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from mednexus.agents.base import BaseAgent
from mednexus.models.agent_messages import AgentRole, TaskAssignment, TaskResult


class VisionSpecialistAgent(BaseAgent):
    """Processes medical images and produces structured diagnostic findings."""

    role = AgentRole.VISION_SPECIALIST

    _SYSTEM_PROMPT = (
        "You are a board-certified radiologist AI assistant. You analyse medical "
        "images and produce structured findings.  Always include:\n"
        "- Anatomical region\n"
        "- Observations (normal & abnormal)\n"
        "- Impression (summary diagnosis)\n"
        "- Confidence score (0.0–1.0)\n\n"
        "Respond ONLY in valid JSON with keys: "
        "region, observations, impression, confidence, recommendations."
    )

    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Analyse the image referenced by `assignment.file_uri`."""
        self.log.info("vision_analysis_start", file=assignment.file_uri)

        try:
            # Step 1 – read the image bytes through MCP
            image_bytes = await self._read_image(assignment.file_uri)
            image_b64 = base64.b64encode(image_bytes).decode()

            # Step 2 – call GPT-4o multimodal
            result_json = await self._analyse_with_gpt4o(image_b64, assignment.instructions)
            parsed: dict[str, Any] = json.loads(result_json)

            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=True,
                summary=parsed.get("impression", "Analysis complete."),
                structured_output=parsed,
            )

        except Exception as exc:
            self.log.error("vision_analysis_error", error=str(exc))
            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=False,
                error_detail=str(exc),
            )

    # ── Private ──────────────────────────────────────────────

    async def _read_image(self, uri: str) -> bytes:
        """Read image bytes via the MCP Clinical Data Gateway.

        Phase 3: uses ``fetch_medical_image`` for audit logging and
        patient-scoped access control when a patient_id is extractable.
        Falls back to the raw MCP backend for non-patient-prefixed URIs.
        """
        import re

        filename = uri.split("/")[-1].split("\\")[-1]
        m = re.match(r"^(P\d{4,})", filename, re.IGNORECASE)

        if m:
            from mednexus.mcp.clinical_gateway import get_clinical_gateway

            gw = get_clinical_gateway()
            result = await gw.fetch_medical_image(
                image_id=filename,
                patient_id=m.group(1).upper(),
                agent_id=self.agent_id,
            )
            import base64 as _b64

            return _b64.b64decode(result["content_base64"])

        # Fallback: direct MCP read (legacy / non-patient files)
        from mednexus.mcp import create_mcp_server

        mcp = create_mcp_server()
        return await mcp.read_bytes(uri)

    async def _analyse_with_gpt4o(self, image_b64: str, extra_instructions: str) -> str:
        """Send the image to GPT-4o Vision and return the raw JSON string."""
        from mednexus.services.llm_client import get_llm_client

        client = get_llm_client()
        return await client.chat_with_image(
            system_prompt=self._SYSTEM_PROMPT,
            user_prompt=extra_instructions or "Analyse this medical image.",
            image_b64=image_b64,
            response_format={"type": "json_object"},
        )
