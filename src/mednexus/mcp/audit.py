"""HIPAA-compliant audit logger for all MCP server requests.

Every tool invocation and resource access made by any agent through the
Clinical Data Gateway is logged with:
  - Requesting agent identity
  - Patient ID scoped to the request
  - Operation name and parameters
  - Timestamp (UTC)
  - Success / failure result

In production this would forward to Azure Monitor / Log Analytics.
During development it writes structured JSON to both structlog and a
local audit file for easy inspection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("mcp.audit")

_AUDIT_DIR = Path("data/audit")


class MCPAuditLogger:
    """Structured audit trail for every MCP gateway interaction."""

    def __init__(self, audit_dir: Path | str = _AUDIT_DIR) -> None:
        self._dir = Path(audit_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "mcp_audit.jsonl"

    def log(
        self,
        *,
        operation: str,
        agent_id: str,
        patient_id: str,
        params: dict[str, Any] | None = None,
        result_summary: str = "ok",
        success: bool = True,
    ) -> None:
        """Persist a single audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "agent_id": agent_id,
            "patient_id": patient_id,
            "params": params or {},
            "result_summary": result_summary,
            "success": success,
        }
        # Structured log (goes to console / Azure Monitor)
        logger.info(
            "mcp_audit",
            **entry,
        )
        # Append to local JSONL file (survives restarts, easy to grep)
        with self._file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read the last *limit* audit entries (newest-first)."""
        if not self._file.exists():
            return []
        lines = self._file.read_text(encoding="utf-8").strip().splitlines()
        entries = [json.loads(line) for line in lines[-limit:]]
        entries.reverse()
        return entries


# Singleton
_audit_instance: MCPAuditLogger | None = None


def get_audit_logger() -> MCPAuditLogger:
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = MCPAuditLogger()
    return _audit_instance
