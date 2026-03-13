"""Agent Framework workflow wrapper for the Vision Specialist."""

from __future__ import annotations

import threading

import structlog
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from typing_extensions import Never

from mednexus.agents.vision_specialist import VisionSpecialistAgent
from mednexus.models.agent_messages import TaskAssignment, TaskResult
from mednexus.observability import mark_span_failure, start_span

logger = structlog.get_logger()

_lock = threading.Lock()
_workflow = None


class VisionSpecialistExecutor(Executor):
    """Framework executor that delegates to the existing vision business logic."""

    def __init__(self) -> None:
        super().__init__(id="vision-specialist-executor")
        self._agent = VisionSpecialistAgent()

    @handler
    async def process(self, assignment: TaskAssignment, ctx: WorkflowContext[Never, TaskResult]) -> None:
        with start_span(
            "workflow.vision_specialist",
            tracer_name="workflow",
            attributes={
                "mednexus.patient_id": assignment.patient_id,
                "mednexus.task_id": assignment.task_id,
                "mednexus.agent": "vision_specialist",
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
                "vision_workflow_completed",
                patient_id=assignment.patient_id,
                task_id=assignment.task_id,
                success=result.success,
            )
            await ctx.yield_output(result)


def get_vision_workflow():
    """Return a singleton Agent Framework workflow for vision tasks."""
    global _workflow

    if _workflow is not None:
        return _workflow

    with _lock:
        if _workflow is None:
            executor = VisionSpecialistExecutor()
            _workflow = WorkflowBuilder(
                name="mednexus-vision-specialist",
                description="Agent Framework workflow for medical image analysis.",
                start_executor=executor,
            ).build()
    return _workflow


async def run_vision_workflow(assignment: TaskAssignment) -> TaskResult:
    """Execute the vision workflow and return its TaskResult."""
    workflow = get_vision_workflow()
    run_result = await workflow.run(assignment)
    outputs = run_result.get_outputs()
    if not outputs:
        raise RuntimeError("Vision workflow completed without a TaskResult output.")
    result = outputs[-1]
    if not isinstance(result, TaskResult):
        raise TypeError(f"Vision workflow returned unexpected output type: {type(result)}")
    return result
