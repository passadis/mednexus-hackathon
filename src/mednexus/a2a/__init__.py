"""A2A (Agent-to-Agent) Protocol – in-process event bus.

This bus routes ``A2AMessage`` instances between agents and broadcasts
them to any connected WebSocket observers (the AGUI "Agent Chatter" pane).

Production note: This in-process bus can be replaced with Azure Service Bus
or Event Grid for distributed deployments without changing agent code.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Awaitable

import structlog

from mednexus.models.agent_messages import A2AMessage, AgentRole

logger = structlog.get_logger()

# Type alias for WebSocket broadcast callback
BroadcastCallback = Callable[[dict[str, Any]], Awaitable[None]]


class A2ABus:
    """In-process message router connecting all MedNexus agents."""

    def __init__(self) -> None:
        self._agents: dict[AgentRole, Any] = {}  # role → BaseAgent instance
        self._message_log: list[A2AMessage] = []
        self._observers: list[BroadcastCallback] = []
        self._lock = asyncio.Lock()

    # ── Agent registration ───────────────────────────────────

    def register(self, agent: Any) -> None:
        """Register an agent with the bus (called at startup)."""
        from mednexus.agents.base import BaseAgent

        if not isinstance(agent, BaseAgent):
            raise TypeError(f"Expected BaseAgent, got {type(agent)}")
        self._agents[agent.role] = agent
        agent._bus = self
        logger.info("agent_registered", role=agent.role.value, agent_id=agent.agent_id)

    # ── Message routing ──────────────────────────────────────

    async def route(self, msg: A2AMessage) -> None:
        """Route a message to the target agent and notify all observers."""
        async with self._lock:
            self._message_log.append(msg)

        # Deliver to the target agent's inbox
        target = self._agents.get(msg.receiver)
        if target is not None:
            target.enqueue(msg)
            logger.info(
                "a2a_message_routed",
                sender=msg.sender.value,
                receiver=msg.receiver.value,
                type=msg.type.value,
                patient=msg.patient_id,
            )
        else:
            logger.warning("a2a_no_receiver", receiver=msg.receiver.value)

        # Broadcast to WebSocket observers (Agent Chatter pane)
        event = {
            "event": "a2a_message",
            "data": msg.model_dump(mode="json"),
        }
        await self._broadcast(event)

    # ── Observer pattern (WebSocket clients) ─────────────────

    def add_observer(self, callback: BroadcastCallback) -> None:
        self._observers.append(callback)

    def remove_observer(self, callback: BroadcastCallback) -> None:
        self._observers = [o for o in self._observers if o is not callback]

    async def _broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all connected WebSocket observers."""
        for cb in self._observers:
            try:
                await cb(event)
            except Exception as exc:
                logger.warning("broadcast_error", error=str(exc))

    # ── Introspection ────────────────────────────────────────

    @property
    def message_count(self) -> int:
        return len(self._message_log)

    @property
    def registered_agents(self) -> list[str]:
        return [r.value for r in self._agents]

    def get_recent_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the last N messages as dicts (for the API)."""
        return [m.model_dump(mode="json") for m in self._message_log[-limit:]]


# ── Singleton ────────────────────────────────────────────────
_bus_instance: A2ABus | None = None


def get_a2a_bus() -> A2ABus:
    """Get or create the singleton A2A bus."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = A2ABus()
    return _bus_instance
