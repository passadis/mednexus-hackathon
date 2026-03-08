"""Tests for the A2A event bus."""

from __future__ import annotations

import asyncio

import pytest

from mednexus.a2a import A2ABus
from mednexus.models.agent_messages import A2AMessage, AgentRole, MessageType


@pytest.fixture
def bus() -> A2ABus:
    """Return a fresh A2ABus instance (not the global singleton)."""
    return A2ABus()


class TestA2ABus:
    @pytest.mark.asyncio
    async def test_send_and_receive(self, bus: A2ABus) -> None:
        """Messages sent to a registered agent appear in its inbox."""

        class _FakeAgent:
            role = AgentRole.VISION_SPECIALIST
            _inbox: asyncio.Queue = asyncio.Queue()

        agent = _FakeAgent()
        bus.register(agent)  # type: ignore[arg-type]

        msg = A2AMessage(
            sender=AgentRole.ORCHESTRATOR,
            receiver=AgentRole.VISION_SPECIALIST,
            message_type=MessageType.TASK_ASSIGN,
            payload={"file_uri": "test.png"},
        )
        await bus.send(msg)

        received = agent._inbox.get_nowait()
        assert received.payload["file_uri"] == "test.png"

    @pytest.mark.asyncio
    async def test_observer_notified(self, bus: A2ABus) -> None:
        """Observers receive broadcasts of every message."""
        received_events: list[dict] = []

        async def observer(event: dict) -> None:
            received_events.append(event)

        bus.add_observer(observer)

        msg = A2AMessage(
            sender=AgentRole.ORCHESTRATOR,
            receiver=AgentRole.CLINICAL_SORTER,
            message_type=MessageType.STATUS_UPDATE,
            payload={"status": "processing"},
        )
        await bus.send(msg)

        # Allow event loop to process
        await asyncio.sleep(0.01)
        assert len(received_events) >= 1

    def test_message_history(self, bus: A2ABus) -> None:
        """get_recent_messages returns logged messages."""
        # Directly manipulate the log for a sync test
        bus._message_log.append({"test": True})
        history = bus.get_recent_messages(10)
        assert any(m.get("test") for m in history)
