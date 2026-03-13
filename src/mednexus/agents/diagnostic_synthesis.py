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
    Modality,
    SynthesisReport,
)


class DiagnosticSynthesisAgent(BaseAgent):
    """Synthesises multi-modal findings into a unified diagnostic report."""

    role = AgentRole.DIAGNOSTIC_SYNTHESIS

    _SYSTEM_PROMPT = (
        "You are a senior clinical decision-support AI. You perform Cross-Modality "
        "Checks across radiology images, clinical text, audio transcripts, and labs.\n\n"
        "CRITICAL GROUNDING RULES:\n"
        "1. Use ONLY the findings explicitly provided below.\n"
        "2. NEVER invent symptoms, patient statements, lab values, transcripts, or other modalities that are not present.\n"
        "3. If only one modality is present, do NOT fabricate cross-modality correlations.\n"
        "4. If audio, text, or lab findings are absent, state that cross-modality comparison is limited by available data.\n\n"
        "Your tasks:\n"
        "1. Summarize the available findings accurately.\n"
        "2. Compare modalities ONLY when two or more modalities are actually present.\n"
        "3. Identify discrepancies ONLY when supported by the provided findings.\n"
        "4. Produce actionable recommendations grounded in the available evidence.\n\n"
        "Respond ONLY in valid JSON with these keys:\n"
        "- summary (string): 2-3 paragraph overall clinical narrative grounded only in the provided findings\n"
        "- cross_modality_notes (string): a single paragraph describing cross-modality observations, "
        "correlations ONLY among modalities that are actually present. If only one modality is present, say that no cross-modality correlation can be made from the available data. MUST be a string, not a list.\n"
        "- discrepancies (array of objects): each with {finding_a_id, finding_b_id, description, severity}. "
        "Use the finding IDs from the findings list below. severity is one of: low, medium, high, critical. "
        "If no supported discrepancies are present, return an empty array [].\n"
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
            modalities_present = sorted({f.modality.value for f in ctx.findings})

            # Build the full findings text
            findings_text = self._format_findings(ctx)

            raw = await self.call_llm(
                system_prompt=self._SYSTEM_PROMPT,
                user_prompt=(
                    f"Patient ID: {ctx.patient.patient_id}\n"
                    f"Patient Name: {ctx.patient.name}\n\n"
                    f"Available modalities: {', '.join(modalities_present) if modalities_present else 'none'}\n"
                    f"Finding count: {len(ctx.findings)}\n"
                    "If only one modality is available, keep cross_modality_notes limited to that fact and return no discrepancies.\n\n"
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
