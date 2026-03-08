"""Clinical Context – the central state object shared across all agents.

This schema is persisted in Azure Cosmos DB and passed between agents during
A2A handoffs.  Every mutation is timestamped and attributed to an agent role
so the full provenance chain is auditable.

Architecture (Episode-Based)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each patient may have multiple **Episodes of Care**.  An episode groups the
files, findings, synthesis and approval for a single clinical incident (e.g.
"Chest evaluation – 2026-01-15" vs "Shoulder pain – 2026-03-03").  A
*cross-episode intelligence* summary is produced automatically once two or
more episodes exist, letting the agents detect longitudinal patterns while
keeping per-visit diagnoses clean and self-contained.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────────────────────────


class ContextStatus(StrEnum):
    """Lifecycle status tracked in Cosmos DB – prevents agents from colliding."""

    INTAKE = "intake"
    WAITING_FOR_RADIOLOGY = "waiting_for_radiology_report"
    WAITING_FOR_HISTORY = "waiting_for_patient_history"
    WAITING_FOR_TRANSCRIPT = "waiting_for_audio_transcript"
    CROSS_MODALITY_CHECK = "cross_modality_check"
    SYNTHESIS_COMPLETE = "synthesis_complete"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"  # Phase 3: MD has signed off
    FINALIZED = "finalized"


class Modality(StrEnum):
    """Data modalities the system can handle."""

    CLINICAL_TEXT = "clinical_text"
    RADIOLOGY_IMAGE = "radiology_image"
    AUDIO_TRANSCRIPT = "audio_transcript"
    LAB_RESULT = "lab_result"


# ── Sub-Models ───────────────────────────────────────────────────────────────


class PatientDemographics(BaseModel):
    """Basic patient identifiers."""

    patient_id: str
    name: str = ""
    date_of_birth: str = ""
    gender: str = ""
    mrn: str = ""  # Medical Record Number


class ClinicalFinding(BaseModel):
    """A single finding produced by one of the specialist agents."""

    finding_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    modality: Modality
    source_agent: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Discrepancy(BaseModel):
    """A discrepancy found during cross-modality comparison."""

    finding_a_id: str = ""
    finding_b_id: str = ""
    description: str
    severity: str = "medium"  # low | medium | high | critical


class SynthesisReport(BaseModel):
    """Final diagnostic synthesis produced by the Synthesis Agent."""

    report_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    summary: str = ""
    cross_modality_notes: str = ""
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_by: str = "diagnostic_synthesis_agent"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("cross_modality_notes", mode="before")
    @classmethod
    def _coerce_notes(cls, v: object) -> str:
        """GPT-4o sometimes returns a list instead of a single string."""
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        return str(v) if v is not None else ""

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, v: object) -> str:
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        return str(v) if v is not None else ""


class AgentActivity(BaseModel):
    """Audit log entry – one per agent action."""

    agent: str
    action: str
    detail: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Episode of Care ──────────────────────────────────────────────────────────


class Episode(BaseModel):
    """A self-contained clinical episode (visit / incident).

    Each episode owns its own findings, synthesis and approval state so that
    the doctor sees a clear per-incident view while the agents can still
    detect cross-episode patterns.
    """

    episode_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    label: str = ""                          # e.g. "Shoulder Pain"
    status: ContextStatus = ContextStatus.INTAKE
    findings: list[ClinicalFinding] = Field(default_factory=list)
    ingested_files: list[str] = Field(default_factory=list)
    synthesis: SynthesisReport | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_notes: str = ""
    activity_log: list[AgentActivity] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── helpers ───────────────────────────────────────────────

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def add_finding(self, finding: ClinicalFinding) -> None:
        self.findings.append(finding)
        self.touch()

    def log_activity(self, agent: str, action: str, detail: str = "") -> None:
        self.activity_log.append(AgentActivity(agent=agent, action=action, detail=detail))
        self.touch()


# ── Primary Context ──────────────────────────────────────────────────────────


class ClinicalContext(BaseModel):
    """The master state object persisted in Cosmos DB.

    Design decisions
    ~~~~~~~~~~~~~~~~
    * ``id`` is the Cosmos document id — set to ``patient_id`` for easy lookup.
    * ``partition_key`` mirrors ``patient_id`` (Cosmos partition strategy).
    * ``episodes`` is the primary data structure — each episode owns its own
      findings, synthesis, and approval.
    * Legacy flat fields (``findings``, ``synthesis``, ``ingested_files``,
      ``approved_by``, …) are kept for backward-compat and are auto-migrated
      into a single "*Legacy*" episode on first load if ``episodes`` is empty.
    * ``cross_episode_summary`` is the holistic intelligence across all
      episodes — produced by the synthesis agent after episode synthesis.
    * ``activity_log`` gives full A2A traceability (global level).
    """

    # Cosmos identifiers
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    partition_key: str = ""

    # Patient info
    patient: PatientDemographics = Field(default_factory=lambda: PatientDemographics(patient_id=""))

    # ── Episode-based architecture ────────────────────────────
    episodes: list[Episode] = Field(default_factory=list)
    active_episode_id: str | None = None
    cross_episode_summary: str = ""

    # Workflow semaphore (overall patient status – derived from active episode)
    status: ContextStatus = ContextStatus.INTAKE

    # Legacy flat fields (kept for backward-compat, migrated on first load)
    findings: list[ClinicalFinding] = Field(default_factory=list)
    ingested_files: list[str] = Field(default_factory=list)
    synthesis: SynthesisReport | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_notes: str = ""

    # Agent activity audit trail (global)
    activity_log: list[AgentActivity] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── helpers ───────────────────────────────────────────────

    def touch(self) -> None:
        """Bump the ``updated_at`` timestamp."""
        self.updated_at = datetime.now(timezone.utc)

    def add_finding(self, finding: ClinicalFinding) -> None:
        """Add finding to the *active* episode (falls back to legacy list)."""
        ep = self.get_active_episode()
        if ep:
            ep.add_finding(finding)
        else:
            self.findings.append(finding)
        self.touch()

    def log_activity(self, agent: str, action: str, detail: str = "") -> None:
        self.activity_log.append(AgentActivity(agent=agent, action=action, detail=detail))
        ep = self.get_active_episode()
        if ep:
            ep.log_activity(agent, action, detail)
        self.touch()

    # ── Episode management ────────────────────────────────────

    def get_active_episode(self) -> Episode | None:
        """Return the current active episode, or None."""
        if not self.active_episode_id:
            return None
        return next(
            (e for e in self.episodes if e.episode_id == self.active_episode_id),
            None,
        )

    def create_episode(self, label: str = "") -> Episode:
        """Create a new episode, make it the active one, and return it."""
        auto_label = label or f"Episode {len(self.episodes) + 1} – {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        ep = Episode(label=auto_label)
        self.episodes.append(ep)
        self.active_episode_id = ep.episode_id
        self.status = ContextStatus.INTAKE
        self.touch()
        return ep

    def ensure_active_episode(self) -> Episode:
        """Return active episode, creating one if none exists."""
        ep = self.get_active_episode()
        if ep is None:
            ep = self.create_episode()
        return ep

    def migrate_legacy_to_episode(self) -> None:
        """If this context has flat findings but no episodes, migrate them."""
        if self.episodes or (not self.findings and not self.ingested_files):
            return  # nothing to migrate

        ep = Episode(
            label="Initial Assessment",
            status=self.status,
            findings=list(self.findings),
            ingested_files=list(self.ingested_files),
            synthesis=self.synthesis,
            approved_by=self.approved_by,
            approved_at=self.approved_at,
            approval_notes=self.approval_notes,
            activity_log=[],
            created_at=self.created_at,
        )
        self.episodes.append(ep)
        self.active_episode_id = ep.episode_id

    # ── Aggregate accessors (for backward-compat in UI/agents) ─

    @property
    def all_findings(self) -> list[ClinicalFinding]:
        """All findings across every episode + legacy."""
        out: list[ClinicalFinding] = list(self.findings)
        for ep in self.episodes:
            out.extend(ep.findings)
        return out

    @property
    def all_ingested_files(self) -> list[str]:
        out: list[str] = list(self.ingested_files)
        for ep in self.episodes:
            out.extend(ep.ingested_files)
        return out

    def to_cosmos_doc(self) -> dict[str, Any]:
        """Serialise to a Cosmos-compatible dict (datetimes → ISO strings)."""
        return self.model_dump(mode="json")

    @classmethod
    def from_cosmos_doc(cls, doc: dict[str, Any]) -> ClinicalContext:
        """Re-hydrate from a Cosmos document."""
        return cls.model_validate(doc)
