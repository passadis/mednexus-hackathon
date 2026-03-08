"""Diagnostic Synthesis Agent – performs cross-modality analysis.

This is the "final mile" agent.  It receives findings from ALL modalities
and produces a unified Synthesis Report, specifically checking for
discrepancies between verbal patient statements and imaging findings.
"""

from __future__ import annotations

import json
from typing import Any

from mednexus.agents.base import BaseAgent
from mednexus.models.agent_messages import AgentRole, TaskAssignment, TaskResult
from mednexus.models.clinical_context import (
    ClinicalContext,
    Discrepancy,
    SynthesisReport,
)


class DiagnosticSynthesisAgent(BaseAgent):
    """Synthesises multi-modal findings into a unified diagnostic report."""

    role = AgentRole.DIAGNOSTIC_SYNTHESIS

    _SYSTEM_PROMPT = (
        "You are a senior clinical decision-support AI. You perform Cross-Modality "
        "Checks across radiology images, clinical text, and patient audio transcripts.\n\n"
        "Your MANDATORY tasks:\n"
        "1. Compare the patient's verbal statements in the audio transcript with "
        "   the clinical findings in the X-ray. Note any discrepancies.\n"
        "2. Cross-reference lab values with imaging findings.\n"
        "3. Identify risk factors that span multiple data sources.\n"
        "4. Produce a unified synthesis with actionable recommendations.\n\n"
        "Respond ONLY in valid JSON with these keys:\n"
        "- summary (string): 2-3 paragraph overall clinical narrative integrating ALL modalities\n"
        "- cross_modality_notes (string): a single paragraph describing cross-modality observations, "
        "correlations between imaging findings and patient-reported symptoms. MUST be a string, not a list.\n"
        "- discrepancies (array of objects): each with {finding_a_id, finding_b_id, description, severity}. "
        "Use the finding IDs from the findings list below. severity is one of: low, medium, high, critical. "
        "If no discrepancies found, return an empty array [].\n"
        "- recommendations (array of strings): 3-5 specific, actionable clinical recommendations. "
        "Include follow-up tests, imaging, specialist referrals, or treatments.\n"
        "- confidence (number): 0.0-1.0\n\n"
        "IMPORTANT: cross_modality_notes must be a single STRING, not a list. "
        "recommendations must be a non-empty list of strings."
    )

    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Synthesise all findings in the clinical context."""
        self.log.info("synthesis_start", patient=assignment.patient_id)

        try:
            ctx = ClinicalContext.from_cosmos_doc(assignment.context_snapshot)

            # Build the full findings text
            findings_text = self._format_findings(ctx)

            raw = await self.call_llm(
                system_prompt=self._SYSTEM_PROMPT,
                user_prompt=(
                    f"Patient ID: {ctx.patient.patient_id}\n"
                    f"Patient Name: {ctx.patient.name}\n\n"
                    f"=== ALL FINDINGS ===\n{findings_text}\n\n"
                    f"Additional instructions: {assignment.instructions}"
                ),
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            parsed: dict[str, Any] = json.loads(raw)

            # Build the SynthesisReport model
            report = SynthesisReport(
                summary=parsed.get("summary", ""),
                cross_modality_notes=parsed.get("cross_modality_notes", ""),
                discrepancies=[
                    Discrepancy(**d) for d in parsed.get("discrepancies", [])
                ],
                recommendations=parsed.get("recommendations", []),
            )

            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=True,
                summary=report.summary,
                structured_output={
                    "report": report.model_dump(mode="json"),
                    "confidence": parsed.get("confidence", 0.0),
                },
            )

        except Exception as exc:
            self.log.error("synthesis_error", error=str(exc))
            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=False,
                error_detail=str(exc),
            )

    @staticmethod
    def _format_findings(ctx: ClinicalContext) -> str:
        """Format all findings into a readable text block for the LLM.

        The orchestrator scopes the context to the active episode before
        dispatching, so ``ctx.findings`` already contains only the relevant
        episode's findings.  We note the active episode label for clarity.
        """
        ep_label = ""
        if ctx.episodes:
            active = ctx.get_active_episode()
            if active:
                ep_label = f"Episode: {active.label}\n\n"

        parts: list[str] = []
        for f in ctx.findings:
            parts.append(
                f"--- Finding ID: {f.finding_id} [{f.modality.value.upper()}] "
                f"from {f.source_agent} (confidence: {f.confidence:.2f}) ---\n"
                f"{f.summary}\n"
                f"Details: {json.dumps(f.details, indent=2)}"
            )
        body = "\n\n".join(parts) if parts else "No findings available."
        return ep_label + body
