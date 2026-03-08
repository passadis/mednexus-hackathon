"""Agent-to-Agent (A2A) message types for inter-agent communication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """All agent roles in the MedNexus system."""

    ORCHESTRATOR = "orchestrator"
    CLINICAL_SORTER = "clinical_sorter"
    VISION_SPECIALIST = "vision_specialist"
    PATIENT_HISTORIAN = "patient_historian"
    DIAGNOSTIC_SYNTHESIS = "diagnostic_synthesis"


class MessageType(StrEnum):
    """A2A message categories."""

    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    STATUS_UPDATE = "status_update"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class A2AMessage(BaseModel):
    """Envelope for every inter-agent message."""

    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: MessageType
    sender: AgentRole
    receiver: AgentRole
    patient_id: str = ""
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = ""  # ties related messages into a conversation


class TaskAssignment(BaseModel):
    """Payload the Orchestrator sends to a specialist."""

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    patient_id: str
    file_uri: str = ""
    file_type: str = ""
    instructions: str = ""
    context_snapshot: dict = Field(default_factory=dict)


class TaskResult(BaseModel):
    """Payload a specialist sends back to the Orchestrator."""

    task_id: str
    patient_id: str
    agent: AgentRole
    success: bool = True
    summary: str = ""
    structured_output: dict = Field(default_factory=dict)
    error_detail: str = ""
