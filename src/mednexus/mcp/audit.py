"""HIPAA-compliant audit logger for all MCP server requests.

Every tool invocation and resource access made by any agent through the
Clinical Data Gateway is logged with:
  - Requesting agent identity
  - Patient ID scoped to the request
  - Operation name and parameters
  - Timestamp (UTC)
  - Success / failure result

In production this would forward to Azure Monitor / Log Analytics.
During development it writes minimal metadata to structlog and encrypted
entries to a local audit file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
import structlog

from mednexus.config import settings

logger = structlog.get_logger("mcp.audit")

_AUDIT_DIR = Path("data/audit")


class MCPAuditLogger:
    """Structured audit trail for every MCP gateway interaction."""

    def __init__(
        self,
        audit_dir: Path | str = _AUDIT_DIR,
        encryption_key: str | bytes | None = None,
    ) -> None:
        self._dir = Path(audit_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "mcp_audit.jsonl"
        key = encryption_key or settings.audit_log_encryption_key
        if not key:
            raise ValueError("AUDIT_LOG_ENCRYPTION_KEY must be configured")
        self._cipher = Fernet(key.encode() if isinstance(key, str) else key)

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
        # Do not send patient data or request parameters to console logs.
        logger.info(
            "mcp_audit",
            operation=operation,
            success=success,
        )
        # Append encrypted audit entries to local storage.
        with self._file.open("ab") as f:
            f.write(self._cipher.encrypt(json.dumps(entry).encode("utf-8")) + b"\n")

    def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read the last *limit* audit entries (newest-first)."""
        if not self._file.exists():
            return []
        lines = self._file.read_bytes().splitlines()
        entries = [
            json.loads(self._cipher.decrypt(line))
            for line in lines[-limit:]
            if line
        ]
        entries.reverse()
        return entries


# Singleton
_audit_instance: MCPAuditLogger | None = None


def get_audit_logger() -> MCPAuditLogger:
    global _audit_instance
    if _audit_instance is None:
        _audit_instance = MCPAuditLogger()
    return _audit_instance
