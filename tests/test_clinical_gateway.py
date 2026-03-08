"""Tests for Phase 3 – Clinical Data Gateway MCP server & Audit Logger."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mednexus.mcp.audit import MCPAuditLogger
from mednexus.mcp.clinical_gateway import (
    CLINICAL_PROTOCOL,
    TOOL_DEFINITIONS,
    ClinicalDataGateway,
)
from mednexus.mcp.local_fs import LocalFileSystemMCP


# ── Audit Logger ─────────────────────────────────────────────


class TestMCPAuditLogger:
    @pytest.fixture
    def audit_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "audit"

    def test_log_and_read(self, audit_dir: Path) -> None:
        logger = MCPAuditLogger(log_dir=str(audit_dir))
        logger.log(
            operation="get_patient_records",
            agent_id="clinical_sorter",
            patient_id="P1234",
            params={"patient_id": "P1234"},
            result_summary="found 3 files",
            success=True,
        )
        entries = logger.get_recent(10)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["operation"] == "get_patient_records"
        assert entry["agent_id"] == "clinical_sorter"
        assert entry["patient_id"] == "P1234"
        assert entry["success"] is True

    def test_multiple_entries_ordered_newest_first(self, audit_dir: Path) -> None:
        logger = MCPAuditLogger(log_dir=str(audit_dir))
        for i in range(5):
            logger.log(
                operation=f"op_{i}",
                agent_id="test",
                patient_id="P0001",
                params={},
                result_summary=f"result {i}",
                success=True,
            )
        recent = logger.get_recent(3)
        assert len(recent) == 3
        assert recent[0]["operation"] == "op_4"  # newest first


# ── Tool Definitions ─────────────────────────────────────────


class TestToolDefinitions:
    def test_tool_names(self) -> None:
        names = [t["name"] for t in TOOL_DEFINITIONS]
        assert "get_patient_records" in names
        assert "fetch_medical_image" in names

    def test_tool_schemas_valid(self) -> None:
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert tool["parameters"]["type"] == "object"


# ── Clinical Data Gateway ────────────────────────────────────


class TestClinicalDataGateway:
    @pytest.fixture
    def gateway(self, tmp_path: Path) -> ClinicalDataGateway:
        """Gateway backed by a temp directory with sample patient files."""
        # Create patient files
        (tmp_path / "P1234_chest_xray.png").write_bytes(b"\x89PNG_fake")
        (tmp_path / "P1234_report.pdf").write_bytes(b"%PDF-fake")
        (tmp_path / "P5678_mri.png").write_bytes(b"\x89PNG_mri")

        mcp = LocalFileSystemMCP(str(tmp_path))
        return ClinicalDataGateway(mcp_server=mcp)

    @pytest.mark.asyncio
    async def test_get_patient_records(self, gateway: ClinicalDataGateway) -> None:
        result = await gateway.get_patient_records("P1234", agent_id="test")
        assert result["patient_id"] == "P1234"
        assert result["total_files"] == 2
        assert "image" in result["files_by_modality"] or "other" in result["files_by_modality"]

    @pytest.mark.asyncio
    async def test_get_patient_records_no_files(self, gateway: ClinicalDataGateway) -> None:
        result = await gateway.get_patient_records("PXXXX", agent_id="test")
        assert result["total_files"] == 0

    @pytest.mark.asyncio
    async def test_fetch_medical_image(self, gateway: ClinicalDataGateway) -> None:
        result = await gateway.fetch_medical_image(
            "P1234_chest_xray.png", "P1234", agent_id="test"
        )
        assert result["image_id"] == "P1234_chest_xray.png"
        assert result["content_type"] == "image/png"
        assert len(result["data_base64"]) > 0

    @pytest.mark.asyncio
    async def test_fetch_medical_image_cross_patient_blocked(
        self, gateway: ClinicalDataGateway
    ) -> None:
        """Attempting to fetch another patient's image raises PermissionError."""
        with pytest.raises(PermissionError, match="Cross-patient"):
            await gateway.fetch_medical_image(
                "P5678_mri.png", "P1234", agent_id="test"
            )

    def test_get_clinical_protocol(self, gateway: ClinicalDataGateway) -> None:
        proto = gateway.get_resource("clinical_protocol")
        assert isinstance(proto, str)
        assert "Patient intake" in proto or len(proto) > 50

    def test_get_unknown_resource(self, gateway: ClinicalDataGateway) -> None:
        with pytest.raises(KeyError):
            gateway.get_resource("nonexistent")

    @pytest.mark.asyncio
    async def test_call_tool_dispatch(self, gateway: ClinicalDataGateway) -> None:
        result = await gateway.call_tool(
            "get_patient_records",
            {"patient_id": "P1234"},
            agent_id="test",
        )
        assert result["patient_id"] == "P1234"

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self, gateway: ClinicalDataGateway) -> None:
        with pytest.raises(ValueError, match="Unknown tool"):
            await gateway.call_tool("bad_tool", {}, agent_id="test")
