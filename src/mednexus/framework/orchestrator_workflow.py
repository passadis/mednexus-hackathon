"""Primary Agent Framework orchestration runtime for MedNexus uploads."""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any

import structlog
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel
from typing_extensions import Never

from mednexus.a2a import A2ABus, get_a2a_bus
from mednexus.agents.orchestrator import OrchestratorAgent
from mednexus.framework.historian_workflow import run_historian_workflow
from mednexus.framework.synthesis_workflow import run_synthesis_workflow
from mednexus.framework.vision_workflow import run_vision_workflow
from mednexus.models.agent_messages import AgentRole, TaskAssignment, TaskResult
from mednexus.models.clinical_context import (
    ClinicalContext,
    ClinicalFinding,
    ContextStatus,
    Discrepancy,
    Episode,
    Modality,
    SynthesisReport,
)
from mednexus.models.medical_files import FileType, MedicalFile
from mednexus.observability import mark_span_failure, start_span
from mednexus.services.cosmos_client import get_cosmos_manager

logger = structlog.get_logger()


class OrchestrationRequest(BaseModel):
    """Workflow input for a single uploaded file."""

    task_id: str
    patient_id: str
    episode_id: str
    filename: str
    file_uri: str
    file_type: str


_lock = threading.Lock()
_workflow = None


class OrchestrationExecutor(Executor):
    """Coordinates specialist workflows for a single file upload."""

    def __init__(self) -> None:
        super().__init__(id="orchestration-executor")
        self._bus = get_a2a_bus()
        self._helper = OrchestratorAgent()

    @handler
    async def process(self, request: OrchestrationRequest, ctx: WorkflowContext[Never, str]) -> None:
        with start_span(
            "workflow.primary_orchestration",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": request.patient_id,
                "mednexus.episode_id": request.episode_id,
                "mednexus.task_id": request.task_id,
                "mednexus.file_type": request.file_type,
                "mednexus.filename": request.filename,
            },
        ) as span:
            try:
                cosmos = get_cosmos_manager()
                clinical_ctx = await cosmos.get_context(request.patient_id)
                if clinical_ctx is None:
                    raise RuntimeError(f"Patient context not found for {request.patient_id}")

                episode = next(
                    (ep for ep in clinical_ctx.episodes if ep.episode_id == request.episode_id),
                    None,
                )
                if episode is None:
                    raise RuntimeError(f"Episode {request.episode_id} not found for {request.patient_id}")

                target_role = OrchestratorAgent._FILE_ROUTING.get(FileType(request.file_type))
                if target_role is None:
                    raise RuntimeError(f"Unsupported file type for orchestration: {request.file_type}")
                if span is not None:
                    span.set_attribute("mednexus.target_agent", target_role.value)

                await self._emit_status(
                    "specialist_started",
                    {
                        "patient_id": request.patient_id,
                        "episode_id": request.episode_id,
                        "agent": target_role.value,
                        "task_id": request.task_id,
                    },
                )

                assignment = TaskAssignment(
                    task_id=request.task_id,
                    patient_id=request.patient_id,
                    file_uri=request.file_uri,
                    file_type=request.file_type,
                    instructions=OrchestratorAgent._build_instructions(FileType(request.file_type)),
                    context_snapshot=clinical_ctx.model_dump(mode="json"),
                )

                result = await self._run_specialist(target_role, assignment)
                clinical_ctx = await self._apply_specialist_result(clinical_ctx, episode, result)
                await cosmos.upsert_context(clinical_ctx)
                await self._emit_status(
                    "context_updated",
                    {"patient_id": request.patient_id},
                )
                await ctx.yield_output(request.task_id)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

    async def _run_specialist(self, target_role: AgentRole, assignment: TaskAssignment) -> TaskResult:
        with start_span(
            "workflow.specialist_dispatch",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": assignment.patient_id,
                "mednexus.task_id": assignment.task_id,
                "mednexus.agent": target_role.value,
                "mednexus.file_type": assignment.file_type,
            },
        ) as span:
            try:
                if target_role == AgentRole.VISION_SPECIALIST:
                    return await run_vision_workflow(assignment)
                if target_role == AgentRole.PATIENT_HISTORIAN:
                    return await run_historian_workflow(assignment)
                raise RuntimeError(f"Unsupported specialist target: {target_role.value}")
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

    async def _apply_specialist_result(
        self,
        clinical_ctx: ClinicalContext,
        episode: Episode,
        result: TaskResult,
    ) -> ClinicalContext:
        if not result.success:
            clinical_ctx.log_activity(
                agent="orchestrator_workflow",
                action="result_failed",
                detail=f"Error from {result.agent.value}: {result.error_detail or 'unknown'}"[:200],
            )
            return clinical_ctx

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
        episode.add_finding(finding)
        clinical_ctx.status = episode.status
        clinical_ctx.log_activity(
            agent="orchestrator_workflow",
            action="result_received",
            detail=f"[{episode.label}] Finding from {result.agent.value}: {result.summary[:120]}",
        )

        await self._emit_status(
            "specialist_completed",
            {
                "patient_id": clinical_ctx.patient.patient_id,
                "episode_id": episode.episode_id,
                "agent": result.agent.value,
                "summary": result.summary,
            },
        )

        await self._maybe_run_synthesis(clinical_ctx, episode)
        return clinical_ctx

    async def _maybe_run_synthesis(self, clinical_ctx: ClinicalContext, episode: Episode) -> None:
        modalities_present = {finding.modality for finding in episode.findings}
        has_both = {Modality.RADIOLOGY_IMAGE, Modality.CLINICAL_TEXT}.issubset(modalities_present)
        all_done_with_findings = len(episode.findings) > 0

        if not (has_both or all_done_with_findings):
            return

        with start_span(
            "workflow.synthesis_dispatch",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": clinical_ctx.patient.patient_id,
                "mednexus.episode_id": episode.episode_id,
                "mednexus.modalities": sorted(f.modality.value for f in episode.findings),
                "mednexus.findings_count": len(episode.findings),
            },
        ) as span:
            try:
                episode.status = ContextStatus.CROSS_MODALITY_CHECK
                clinical_ctx.status = episode.status
                clinical_ctx.log_activity(
                    agent="orchestrator_workflow",
                    action="trigger_synthesis",
                    detail=f"[{episode.label}] Triggering per-episode synthesis",
                )
                await self._emit_status(
                    "synthesis_started",
                    {
                        "patient_id": clinical_ctx.patient.patient_id,
                        "episode_id": episode.episode_id,
                    },
                )

                scoped = clinical_ctx.model_copy(deep=True)
                scoped.findings = list(episode.findings)
                scoped.ingested_files = list(episode.ingested_files)

                modalities = sorted({f.modality.value for f in episode.findings})
                task = TaskAssignment(
                    patient_id=clinical_ctx.patient.patient_id,
                    instructions=(
                        f"You are the Diagnostic Synthesis Agent. You are synthesising "
                        f"findings for **{episode.label}** (episode {episode.episode_id}).\n\n"
                        f"Available modalities in this episode: {', '.join(modalities) if modalities else 'none'}.\n\n"
                        "Grounding rules:\n"
                        "1. Use only the findings present in this episode.\n"
                        "2. Do not invent patient symptoms, verbal statements, labs, or transcripts that are not present.\n"
                        "3. If only one modality is present, produce a unimodal synthesis and state that cross-modality comparison is limited by available data.\n"
                        "4. Only report discrepancies when they are supported by the findings provided.\n\n"
                        "Produce a unified Synthesis Report with recommendations.\n"
                        "Be precise. Flag supported inconsistencies with severity ratings."
                    ),
                    context_snapshot=scoped.model_dump(mode="json"),
                )

                result = await run_synthesis_workflow(task)
                if span is not None:
                    span.set_attribute("mednexus.success", result.success)
                if not result.success:
                    clinical_ctx.log_activity(
                        agent="orchestrator_workflow",
                        action="synthesis_failed",
                        detail=result.error_detail[:200],
                    )
                    return

                report_data = result.structured_output.get("report", {})
                synthesis = SynthesisReport(
                    summary=report_data.get("summary", result.summary),
                    cross_modality_notes=report_data.get("cross_modality_notes", ""),
                    discrepancies=[
                        Discrepancy(**disc)
                        for disc in report_data.get("discrepancies", [])
                        if isinstance(disc, dict)
                    ],
                    recommendations=report_data.get("recommendations", []),
                )

                episode.synthesis = synthesis
                episode.status = ContextStatus.SYNTHESIS_COMPLETE
                episode.touch()
                clinical_ctx.synthesis = synthesis
                clinical_ctx.status = ContextStatus.SYNTHESIS_COMPLETE
                clinical_ctx.log_activity(
                    agent="orchestrator_workflow",
                    action="synthesis_complete",
                    detail=f"[{episode.label}] Synthesis report received: {result.summary[:120]}",
                )

                await self._emit_status(
                    "synthesis_completed",
                    {
                        "patient_id": clinical_ctx.patient.patient_id,
                        "episode_id": episode.episode_id,
                        "summary": result.summary,
                    },
                )

                await self._helper._maybe_trigger_cross_episode(clinical_ctx)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

    async def _emit_status(self, event_name: str, data: dict[str, Any]) -> None:
        await self._bus.broadcast_event(event_name, data)


def get_orchestration_workflow():
    """Return a singleton workflow for primary upload orchestration."""
    global _workflow

    if _workflow is not None:
        return _workflow

    with _lock:
        if _workflow is None:
            executor = OrchestrationExecutor()
            _workflow = WorkflowBuilder(
                name="mednexus-primary-orchestration",
                description="Primary Agent Framework workflow for uploaded file orchestration.",
                start_executor=executor,
            ).build()
    return _workflow


class OrchestratorWorkflowRuntime:
    """Upload-facing orchestrator facade backed by Agent Framework."""

    def __init__(self) -> None:
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def ingest_file(
        self,
        file: MedicalFile,
        ctx: ClinicalContext,
        *,
        episode_id: str | None = None,
    ) -> str:
        with start_span(
            "workflow.ingest_dispatch",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": ctx.patient.patient_id,
                "mednexus.file_type": file.file_type.value,
                "mednexus.filename": file.filename,
                "mednexus.episode_id": episode_id,
            },
        ) as span:
            try:
                target_role = OrchestratorAgent._FILE_ROUTING.get(file.file_type)
                if target_role is None:
                    logger.warning("unsupported_file_type", file_type=file.file_type)
                    return ""

                if episode_id:
                    episode = next((ep for ep in ctx.episodes if ep.episode_id == episode_id), None)
                    if episode:
                        ctx.active_episode_id = episode.episode_id
                episode = ctx.ensure_active_episode()

                if episode.synthesis is not None:
                    episode.synthesis = None
                    episode.status = ContextStatus.INTAKE
                    ctx.log_activity(
                        agent="orchestrator_workflow",
                        action="synthesis_reset",
                        detail=f"[{episode.label}] New file added — synthesis will re-run",
                    )

                OrchestratorAgent._transition_status(episode, file.file_type)
                ctx.status = episode.status
                episode.ingested_files.append(file.uri)
                task_id = uuid.uuid4().hex[:12]
                if span is not None:
                    span.set_attribute("mednexus.target_agent", target_role.value)
                    span.set_attribute("mednexus.task_id", task_id)
                    span.set_attribute("mednexus.episode_id", episode.episode_id)
                ctx.log_activity(
                    agent="orchestrator_workflow",
                    action="dispatch",
                    detail=f"[{episode.label}] Dispatched {file.filename} → {target_role.value} (task {task_id})",
                )

                cosmos = get_cosmos_manager()
                await cosmos.upsert_context(ctx)

                request = OrchestrationRequest(
                    task_id=task_id,
                    patient_id=ctx.patient.patient_id,
                    episode_id=episode.episode_id,
                    filename=file.filename,
                    file_uri=file.uri,
                    file_type=file.file_type.value,
                )
                task = asyncio.create_task(self._run_workflow(request))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
                logger.info(
                    "orchestration_workflow_dispatched",
                    patient_id=ctx.patient.patient_id,
                    episode_id=episode.episode_id,
                    target=target_role.value,
                    task_id=task_id,
                )
                return task_id
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

    async def _run_workflow(self, request: OrchestrationRequest) -> None:
        with start_span(
            "workflow.background_run",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": request.patient_id,
                "mednexus.episode_id": request.episode_id,
                "mednexus.task_id": request.task_id,
            },
        ) as span:
            try:
                workflow = get_orchestration_workflow()
                await workflow.run(request)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise
