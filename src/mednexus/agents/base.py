"""Base agent class – every MedNexus agent inherits from this.

Provides:
  - A2A message send/receive via an in-process event bus.
  - Structured logging bound to agent identity.
  - LLM helper that routes through Azure AI Foundry.
  - Abstract ``handle_task`` that subclasses implement.
"""

from __future__ import annotations

import abc
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from mednexus.models.agent_messages import (
    A2AMessage,
    AgentRole,
    MessageType,
    TaskAssignment,
    TaskResult,
)


class BaseAgent(abc.ABC):
    """Abstract base for all MedNexus agents."""

    role: AgentRole  # set by each subclass

    def __init__(self) -> None:
        self.agent_id: str = f"{self.role.value}-{uuid.uuid4().hex[:6]}"
        self.log = structlog.get_logger().bind(agent=self.agent_id, role=self.role.value)
        self._inbox: asyncio.Queue[A2AMessage] = asyncio.Queue()
        # Will be populated by the A2A bus when agents register
        self._bus: Any | None = None

    # ── A2A messaging ────────────────────────────────────────

    async def send(self, msg: A2AMessage) -> None:
        """Publish a message to the A2A bus."""
        if self._bus is None:
            raise RuntimeError(f"Agent {self.agent_id} is not connected to an A2A bus.")
        await self._bus.route(msg)

    async def receive(self, timeout: float = 30.0) -> A2AMessage | None:
        """Wait for the next message addressed to this agent."""
        try:
            return await asyncio.wait_for(self._inbox.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def enqueue(self, msg: A2AMessage) -> None:
        """Called by the A2A bus to deliver a message."""
        self._inbox.put_nowait(msg)

    # ── LLM helper ───────────────────────────────────────────

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ) -> str:
        """Call Azure OpenAI via the shared client utility."""
        from mednexus.services.llm_client import get_llm_client

        client = get_llm_client()
        return await client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    # ── Lifecycle ────────────────────────────────────────────

    @abc.abstractmethod
    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Process a task delegated by the Orchestrator (or self-initiated)."""

    async def start(self) -> None:
        """Main event loop — listens for incoming A2A messages."""
        self.log.info("agent_started")
        while True:
            msg = await self.receive(timeout=60.0)
            if msg is None:
                continue  # heartbeat window
            if msg.type == MessageType.TASK_ASSIGN:
                assignment = TaskAssignment.model_validate(msg.payload)
                self.log.info("task_received", task_id=assignment.task_id)
                result = await self.handle_task(assignment)
                await self.send(
                    A2AMessage(
                        type=MessageType.TASK_RESULT,
                        sender=self.role,
                        receiver=AgentRole.ORCHESTRATOR,
                        patient_id=assignment.patient_id,
                        payload=result.model_dump(mode="json"),
                        correlation_id=msg.correlation_id,
                    )
                )
