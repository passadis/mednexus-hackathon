"""Agent Framework workflow wrapper for the Diagnostic Synthesis specialist."""

from __future__ import annotations

import threading

import structlog
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never

from mednexus.agents.diagnostic_synthesis import DiagnosticSynthesisAgent
from mednexus.models.agent_messages import TaskAssignment, TaskResult
from mednexus.observability import mark_span_failure, start_span

logger = structlog.get_logger()

_lock = threading.Lock()
_workflow = None


class DiagnosticSynthesisExecutor(Executor):
    """Framework executor that delegates to the existing synthesis business logic."""

    def __init__(self) -> None:
        super().__init__(id="diagnostic-synthesis-executor")
        self._agent = DiagnosticSynthesisAgent()

    @handler
    async def process(self, assignment: TaskAssignment, ctx: WorkflowContext[Never, TaskResult]) -> None:
        with start_span(
            "workflow.diagnostic_synthesis",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": assignment.patient_id,
                "mednexus.task_id": assignment.task_id,
                "mednexus.agent": "diagnostic_synthesis",
                "mednexus.file_type": assignment.file_type,
            },
        ) as span:
            try:
                result = await self._agent.handle_task(assignment)
            except Exception as exc:
                mark_span_failure(span, exc)
                raise

            if span is not None:
                span.set_attribute("mednexus.success", result.success)

            logger.info(
                "synthesis_workflow_completed",
                patient_id=assignment.patient_id,
                task_id=assignment.task_id,
                success=result.success,
            )
            await ctx.yield_output(result)


def get_synthesis_workflow():
    """Return a singleton Agent Framework workflow for synthesis tasks."""
    global _workflow

    if _workflow is not None:
        return _workflow

    with _lock:
        if _workflow is None:
            executor = DiagnosticSynthesisExecutor()
            _workflow = WorkflowBuilder(
                name="mednexus-diagnostic-synthesis",
                description="Agent Framework workflow for diagnostic synthesis generation.",
                start_executor=executor,
            ).build()
    return _workflow


async def run_synthesis_workflow(assignment: TaskAssignment) -> TaskResult:
    """Execute the synthesis workflow and return its TaskResult."""
    workflow = get_synthesis_workflow()
    run_result = await workflow.run(assignment)
    outputs = run_result.get_outputs()
    if not outputs:
        raise RuntimeError("Synthesis workflow completed without a TaskResult output.")
    result = outputs[-1]
    if not isinstance(result, TaskResult):
        raise TypeError(f"Synthesis workflow returned unexpected output type: {type(result)}")
    return result
