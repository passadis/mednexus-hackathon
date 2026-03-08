"""Tests for MCP abstraction layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mednexus.mcp.local_fs import LocalFileSystemMCP


class TestLocalFileSystemMCP:
    @pytest.fixture
    def mcp_dir(self, tmp_path: Path) -> Path:
        """Create a temporary drop-folder with some test files."""
        (tmp_path / "P1234_xray.png").write_bytes(b"\x89PNG_fake_data")
        (tmp_path / "P1234_report.pdf").write_bytes(b"%PDF-1.4 fake")
        return tmp_path

    @pytest.mark.asyncio
    async def test_list_files(self, mcp_dir: Path) -> None:
        mcp = LocalFileSystemMCP(str(mcp_dir))
        files = await mcp.list_files()
        names = [f.name for f in files]
        assert "P1234_xray.png" in names
        assert "P1234_report.pdf" in names

    @pytest.mark.asyncio
    async def test_read_bytes(self, mcp_dir: Path) -> None:
        mcp = LocalFileSystemMCP(str(mcp_dir))
        data = await mcp.read_bytes(str(mcp_dir / "P1234_xray.png"))
        assert data.startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_move_to_processed(self, mcp_dir: Path) -> None:
        mcp = LocalFileSystemMCP(str(mcp_dir))
        uri = str(mcp_dir / "P1234_report.pdf")
        await mcp.move_to_processed(uri)

        # File should no longer be in root
        assert not (mcp_dir / "P1234_report.pdf").exists()
        # Should be in _processed
        assert (mcp_dir / "_processed" / "P1234_report.pdf").exists()

    @pytest.mark.asyncio
    async def test_healthcheck(self, mcp_dir: Path) -> None:
        mcp = LocalFileSystemMCP(str(mcp_dir))
        assert await mcp.healthcheck() is True

    @pytest.mark.asyncio
    async def test_healthcheck_bad_dir(self) -> None:
        mcp = LocalFileSystemMCP("/nonexistent/path/12345")
        assert await mcp.healthcheck() is False
