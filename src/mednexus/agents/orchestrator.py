"""Orchestrator Agent – the "brain" of MedNexus.

Responsibilities:
  1. Accept new files from the Clinical Sorter (via MCP).
  2. Determine which specialist(s) to engage based on file type.
  3. Manage the A2A handoff – dispatch tasks, collect results.
  4. Maintain the Clinical Context in Cosmos DB (single source of truth).
  5. Trigger the Diagnostic Synthesis per-episode when all modalities are gathered.
  6. Produce cross-episode intelligence once an episode synthesis completes.

Design:
  - Uses a state-machine approach driven by episode ``status``.
  - Each status transition is logged for full traceability.
  - Synthesis is scoped per-episode; cross-episode summary is holistic.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from mednexus.agents.base import BaseAgent
from mednexus.models.agent_messages import (
    A2AMessage,
    AgentRole,
    MessageType,
    TaskAssignment,
    TaskResult,
)
from mednexus.models.clinical_context import ClinicalContext, ContextStatus, Episode
from mednexus.models.medical_files import FileType, MedicalFile


class OrchestratorAgent(BaseAgent):
    """Central orchestuation agent that coordinates all specialist agents."""

    role = AgentRole.ORCHESTRATOR

    def __init__(self) -> None:
        super().__init__()
        self._pending_tasks: dict[str, str] = {}   # task_id → episode_id
        self._synthesis_sent: set[str] = set()      # episode_ids already dispatched
        self.log = structlog.get_logger().bind(agent=self.agent_id, role="orchestrator")

    # ── File routing ─────────────────────────────────────────

    _FILE_ROUTING: dict[FileType, AgentRole] = {
        FileType.IMAGE: AgentRole.VISION_SPECIALIST,
        FileType.DICOM: AgentRole.VISION_SPECIALIST,
        FileType.PDF: AgentRole.PATIENT_HISTORIAN,
        FileType.AUDIO: AgentRole.PATIENT_HISTORIAN,  # transcription first, then RAG
        FileType.LAB_CSV: AgentRole.PATIENT_HISTORIAN,
        FileType.TEXT: AgentRole.PATIENT_HISTORIAN,
    }

    # ── Public API (called by the FastAPI layer) ─────────────

    async def ingest_file(
        self, file: MedicalFile, ctx: ClinicalContext, *, episode_id: str | None = None
    ) -> str:
        """Route a new file to the appropriate specialist agent.

        Files are attached to the **active episode**.  If ``episode_id`` is
        supplied the orchestrator activates that specific episode first.

        Returns the ``task_id`` so the caller can track it.
        """
        target_role = self._FILE_ROUTING.get(file.file_type)
        if target_role is None:
            self.log.warning("unsupported_file_type", file_type=file.file_type)
            return ""

        # Resolve episode
        if episode_id:
            ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None)
            if ep:
                ctx.active_episode_id = ep.episode_id
        ep = ctx.ensure_active_episode()

        task = TaskAssignment(
            patient_id=ctx.patient.patient_id,
            file_uri=file.uri,
            file_type=file.file_type.value,
            instructions=self._build_instructions(file.file_type),
            context_snapshot=ctx.model_dump(mode="json"),
        )

        # Update episode status
        self._transition_status(ep, file.file_type)
        ctx.status = ep.status  # mirror at top level
        ep.ingested_files.append(file.uri)
        ctx.log_activity(
            agent=self.agent_id,
            action="dispatch",
            detail=f"[{ep.label}] Dispatched {file.filename} → {target_role.value} (task {task.task_id})",
        )

        # Send A2A message
        correlation = uuid.uuid4().hex
        await self.send(
            A2AMessage(
                type=MessageType.TASK_ASSIGN,
                sender=self.role,
                receiver=target_role,
                patient_id=ctx.patient.patient_id,
                payload=task.model_dump(mode="json"),
                correlation_id=correlation,
            )
        )

        self._pending_tasks[task.task_id] = ep.episode_id
        self.log.info(
            "file_dispatched",
            task_id=task.task_id,
            target=target_role.value,
            file=file.filename,
            episode=ep.episode_id,
        )
        return task.task_id

    async def handle_specialist_result(
        self, result: TaskResult, ctx: ClinicalContext
    ) -> ClinicalContext:
        """Process a result returned by a specialist agent.

        If all expected modalities are in, trigger the per-episode synthesis.
        Synthesis results are stored in the Episode (not re-triggered for the
        same episode).
        """
        from mednexus.models.clinical_context import (
            ClinicalFinding,
            Discrepancy,
            Modality,
            SynthesisReport,
        )

        # Determine which episode this task belongs to
        episode_id = self._pending_tasks.pop(result.task_id, None)
        ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None) if episode_id else None
        if ep is None:
            ep = ctx.get_active_episode()

        # ── Handle synthesis results (terminal for this episode) ──
        if result.agent == AgentRole.DIAGNOSTIC_SYNTHESIS:
            report_data = result.structured_output.get("report", {})
            synthesis = SynthesisReport(
                summary=report_data.get("summary", result.summary),
                cross_modality_notes=report_data.get(
                    "cross_modality_notes", ""
                ),
                discrepancies=[
                    Discrepancy(**d)
                    for d in report_data.get("discrepancies", [])
                    if isinstance(d, dict)
                ],
                recommendations=report_data.get("recommendations", []),
            )

            if ep:
                ep.synthesis = synthesis
                ep.status = ContextStatus.SYNTHESIS_COMPLETE
                ep.touch()
            # Also mirror to legacy field for backward-compat
            ctx.synthesis = synthesis
            ctx.status = ContextStatus.SYNTHESIS_COMPLETE
            ctx.log_activity(
                agent=self.agent_id,
                action="synthesis_complete",
                detail=f"[{ep.label if ep else '?'}] Synthesis report received: {result.summary[:120]}",
            )
            self.log.info(
                "synthesis_complete",
                patient=ctx.patient.patient_id,
                episode=ep.episode_id if ep else None,
            )

            # Trigger cross-episode intelligence if 2+ episodes
            await self._maybe_trigger_cross_episode(ctx)
            return ctx

        # ── Handle specialist results ────────────────────────
        pid = ctx.patient.patient_id

        # Skip failed results
        if not result.success:
            ctx.log_activity(
                agent=self.agent_id,
                action="result_failed",
                detail=f"Error from {result.agent.value}: {result.error_detail or 'unknown'}"[:200],
            )
            self.log.warning(
                "specialist_failed",
                patient=pid,
                agent=result.agent.value,
                error=result.error_detail,
            )
            if ep:
                await self._maybe_trigger_synthesis(ctx, ep)
            return ctx

        modality_map: dict[AgentRole, Modality] = {
            AgentRole.VISION_SPECIALIST: Modality.RADIOLOGY_IMAGE,
            AgentRole.PATIENT_HISTORIAN: Modality.CLINICAL_TEXT,
        }

        modality = modality_map.get(result.agent, Modality.CLINICAL_TEXT)

        finding = ClinicalFinding(
            modality=modality,
            source_agent=result.agent.value,
            summary=result.summary,
            confidence=result.structured_output.get("confidence", 0.0),
            details=result.structured_output,
        )

        # Add to episode
        if ep:
            ep.add_finding(finding)
        else:
            ctx.add_finding(finding)

        ctx.log_activity(
            agent=self.agent_id,
            action="result_received",
            detail=f"[{ep.label if ep else '?'}] Finding from {result.agent.value}: {result.summary[:120]}",
        )

        if ep:
            await self._maybe_trigger_synthesis(ctx, ep)

        self.log.info(
            "result_processed",
            patient=ctx.patient.patient_id,
            status=ctx.status.value,
            pending=len(self._pending_tasks),
            episode=ep.episode_id if ep else None,
        )
        return ctx

    # ── Result listener (runs as a background task) ──────────

    async def start(self) -> None:
        """Listen for TASK_RESULT messages from specialist agents."""
        from mednexus.services.cosmos_client import get_cosmos_manager

        self.log.info("orchestrator_started")
        cosmos = get_cosmos_manager()

        while True:
            msg = await self.receive(timeout=60.0)
            if msg is None:
                continue  # heartbeat

            if msg.type == MessageType.TASK_RESULT:
                result = TaskResult.model_validate(msg.payload)
                patient_id = msg.patient_id or result.patient_id
                self.log.info(
                    "result_received",
                    task_id=result.task_id,
                    agent=result.agent.value,
                    patient=patient_id,
                )

                # Load context, process result, persist
                ctx = await cosmos.get_context(patient_id)
                if ctx is None:
                    self.log.warning("context_not_found", patient_id=patient_id)
                    continue

                ctx = await self.handle_specialist_result(result, ctx)
                await cosmos.upsert_context(ctx)

    # ── Task interface (unused for Orchestrator, but required) ─

    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Orchestrator doesn't receive assignments; it dispatches them."""
        return TaskResult(
            task_id=assignment.task_id,
            patient_id=assignment.patient_id,
            agent=self.role,
            success=True,
            summary="Orchestrator acknowledged.",
        )

    # ── Private helpers ──────────────────────────────────────

    @staticmethod
    def _transition_status(ep: Episode, ftype: FileType) -> None:
        """Move episode to the correct waiting state based on file type."""
        status_map: dict[FileType, ContextStatus] = {
            FileType.IMAGE: ContextStatus.WAITING_FOR_RADIOLOGY,
            FileType.DICOM: ContextStatus.WAITING_FOR_RADIOLOGY,
            FileType.PDF: ContextStatus.WAITING_FOR_HISTORY,
            FileType.TEXT: ContextStatus.WAITING_FOR_HISTORY,
            FileType.AUDIO: ContextStatus.WAITING_FOR_TRANSCRIPT,
            FileType.LAB_CSV: ContextStatus.WAITING_FOR_HISTORY,
        }
        ep.status = status_map.get(ftype, ep.status)

    @staticmethod
    def _build_instructions(ftype: FileType) -> str:
        """Generate specialist-specific instructions."""
        instructions: dict[FileType, str] = {
            FileType.IMAGE: (
                "Analyze this medical image. Identify anatomical structures, any "
                "abnormalities, and provide a structured radiology-style finding. "
                "Rate your confidence 0-1."
            ),
            FileType.DICOM: (
                "Process this DICOM file. Extract metadata and analyze the image. "
                "Provide structured findings with confidence ratings."
            ),
            FileType.PDF: (
                "Extract and summarise key clinical information from this PDF. "
                "Focus on diagnoses, medications, lab values, and clinical history."
            ),
            FileType.TEXT: (
                "Analyze this clinical text document (transcript, notes, or records). "
                "Extract key clinical information: symptoms, diagnoses, medications, "
                "vital signs, and patient history. Provide a structured summary."
            ),
            FileType.AUDIO: (
                "Transcribe this audio recording using Azure Whisper, then extract "
                "clinically relevant statements. Note any symptoms or concerns "
                "mentioned by the patient."
            ),
            FileType.LAB_CSV: (
                "Parse this lab results file. Flag any out-of-range values and "
                "summarise the overall lab picture."
            ),
        }
        return instructions.get(ftype, "Process this file and return structured findings.")

    async def _maybe_trigger_synthesis(self, ctx: ClinicalContext, ep: Episode) -> None:
        """Fire per-episode synthesis once: when both modalities present, OR
        when no pending tasks remain for this episode and we have ≥1 finding."""
        from mednexus.models.clinical_context import Modality

        eid = ep.episode_id
        if eid in self._synthesis_sent or ep.status == ContextStatus.SYNTHESIS_COMPLETE:
            return

        modalities_present = {f.modality for f in ep.findings}
        has_both = {Modality.RADIOLOGY_IMAGE, Modality.CLINICAL_TEXT}.issubset(
            modalities_present
        )
        episode_pending = sum(
            1 for e in self._pending_tasks.values() if e == eid
        )
        all_done_with_findings = episode_pending == 0 and len(ep.findings) > 0

        if has_both or all_done_with_findings:
            self._synthesis_sent.add(eid)
            ep.status = ContextStatus.CROSS_MODALITY_CHECK
            ctx.status = ep.status
            ctx.log_activity(agent=self.agent_id, action="trigger_synthesis",
                             detail=f"[{ep.label}] Triggering per-episode synthesis")
            await self._dispatch_synthesis(ctx, ep)

    async def _dispatch_synthesis(self, ctx: ClinicalContext, ep: Episode) -> None:
        """Send a synthesis task to the Diagnostic Synthesis agent.

        The context_snapshot only includes the active episode's findings
        so the synthesis is scoped to this incident.
        """
        # Build a lightweight context with only this episode's findings
        scoped = ctx.model_copy(deep=True)
        scoped.findings = list(ep.findings)
        scoped.ingested_files = list(ep.ingested_files)

        task = TaskAssignment(
            patient_id=ctx.patient.patient_id,
            instructions=(
                f"You are the Diagnostic Synthesis Agent. You are synthesising "
                f"findings for **{ep.label}** (episode {ep.episode_id}).\n\n"
                f"Perform a Cross-Modality Check:\n"
                "1. Compare the patient's verbal statements in the audio transcript "
                "   with the clinical findings in the X-ray. Are there discrepancies?\n"
                "2. Cross-reference lab values with imaging findings.\n"
                "3. Produce a unified Synthesis Report with recommendations.\n\n"
                "Be precise. Flag any inconsistencies with severity ratings."
            ),
            context_snapshot=scoped.model_dump(mode="json"),
        )
        await self.send(
            A2AMessage(
                type=MessageType.TASK_ASSIGN,
                sender=self.role,
                receiver=AgentRole.DIAGNOSTIC_SYNTHESIS,
                patient_id=ctx.patient.patient_id,
                payload=task.model_dump(mode="json"),
                correlation_id=uuid.uuid4().hex,
            )
        )
        self.log.info("synthesis_dispatched", patient=ctx.patient.patient_id, episode=ep.episode_id)

    async def _maybe_trigger_cross_episode(self, ctx: ClinicalContext) -> None:
        """Generate cross-episode intelligence once 2+ episodes have synthesis."""
        completed = [e for e in ctx.episodes if e.synthesis is not None]
        if len(completed) < 2:
            return

        # Build a concise summary of each episode for the LLM
        parts: list[str] = []
        for ep in completed:
            parts.append(
                f"--- Episode: {ep.label} ({ep.episode_id}) ---\n"
                f"Date: {ep.created_at.isoformat()[:10]}\n"
                f"Findings: {len(ep.findings)}\n"
                f"Synthesis: {ep.synthesis.summary[:300] if ep.synthesis else 'N/A'}\n"
            )
        episodes_text = "\n".join(parts)

        try:
            raw = await self.call_llm(
                system_prompt=(
                    "You are a senior clinical decision-support AI reviewing MULTIPLE "
                    "episodes of care for the same patient. Your job is to determine:\n"
                    "1. Are these episodes clinically related or independent incidents?\n"
                    "2. Are there longitudinal patterns (recurring symptoms, progressive disease)?\n"
                    "3. Should any prior episode findings change the clinical picture?\n\n"
                    "Be concise. 2-3 paragraphs max. If episodes are unrelated, state so clearly."
                ),
                user_prompt=(
                    f"Patient: {ctx.patient.patient_id} ({ctx.patient.name})\n\n"
                    f"{episodes_text}"
                ),
                temperature=0.1,
                max_tokens=1024,
            )
            ctx.cross_episode_summary = raw.strip()
            ctx.log_activity(
                agent=self.agent_id,
                action="cross_episode_intelligence",
                detail=f"Cross-episode analysis produced for {len(completed)} episodes",
            )
            self.log.info(
                "cross_episode_complete",
                patient=ctx.patient.patient_id,
                episode_count=len(completed),
            )
        except Exception as exc:
            self.log.error("cross_episode_error", error=str(exc))
            ctx.cross_episode_summary = ""
