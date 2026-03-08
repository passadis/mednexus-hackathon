"""Tests for core Pydantic models."""

from __future__ import annotations

import json

from mednexus.models.agent_messages import A2AMessage, AgentRole, MessageType
from mednexus.models.clinical_context import (
    ClinicalContext,
    ClinicalFinding,
    ContextStatus,
    PatientDemographics,
)
from mednexus.models.medical_files import FileType, MedicalFile


# ── ClinicalContext ──────────────────────────────────────────


class TestClinicalContext:
    def test_default_status_is_intake(self) -> None:
        ctx = ClinicalContext(patient_id="P0001")
        assert ctx.status == ContextStatus.INTAKE

    def test_cosmos_round_trip(self, sample_context: ClinicalContext) -> None:
        doc = sample_context.to_cosmos_doc()
        restored = ClinicalContext.from_cosmos_doc(doc)
        assert restored.patient_id == sample_context.patient_id
        assert restored.status == sample_context.status

    def test_json_serialisation(self, sample_context: ClinicalContext) -> None:
        payload = sample_context.model_dump_json()
        parsed = json.loads(payload)
        assert parsed["patient_id"] == "P1234"

    def test_findings_list(self, sample_context: ClinicalContext) -> None:
        finding = ClinicalFinding(
            source_agent="vision_specialist",
            modality="xray",
            summary="No abnormalities detected",
            confidence=0.95,
        )
        sample_context.findings.append(finding)
        assert len(sample_context.findings) == 1
        assert sample_context.findings[0].confidence == 0.95


# ── MedicalFile ──────────────────────────────────────────────


class TestMedicalFile:
    def test_classify_png(self) -> None:
        mf = MedicalFile.classify("P1234_chest.png", "file:///data/chest.png")
        assert mf.file_type == FileType.IMAGE

    def test_classify_pdf(self) -> None:
        mf = MedicalFile.classify("report.pdf", "file:///data/report.pdf")
        assert mf.file_type == FileType.PDF

    def test_classify_dicom(self) -> None:
        mf = MedicalFile.classify("scan.dcm", "file:///data/scan.dcm")
        assert mf.file_type == FileType.DICOM

    def test_classify_audio(self) -> None:
        mf = MedicalFile.classify("recording.wav", "file:///data/recording.wav")
        assert mf.file_type == FileType.AUDIO

    def test_classify_csv(self) -> None:
        mf = MedicalFile.classify("labs.csv", "file:///data/labs.csv")
        assert mf.file_type == FileType.LAB_CSV

    def test_classify_unknown(self) -> None:
        mf = MedicalFile.classify("mystery.xyz", "file:///data/mystery.xyz")
        assert mf.file_type == FileType.UNKNOWN


# ── A2A Messages ─────────────────────────────────────────────


class TestA2AMessage:
    def test_create_task_assignment(self) -> None:
        msg = A2AMessage(
            sender=AgentRole.ORCHESTRATOR,
            receiver=AgentRole.VISION_SPECIALIST,
            message_type=MessageType.TASK_ASSIGN,
            payload={"file_uri": "az://container/xray.png"},
        )
        assert msg.sender == AgentRole.ORCHESTRATOR
        assert msg.receiver == AgentRole.VISION_SPECIALIST

    def test_serialisation(self) -> None:
        msg = A2AMessage(
            sender=AgentRole.PATIENT_HISTORIAN,
            receiver=AgentRole.ORCHESTRATOR,
            message_type=MessageType.TASK_RESULT,
            payload={"summary": "Patient history retrieved"},
        )
        data = msg.model_dump()
        assert "sender" in data
        assert "timestamp" in data
