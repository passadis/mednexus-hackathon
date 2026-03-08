"""Abstract base class for MCP (Model Context Protocol) servers.

Any new data backend (SFTP, S3, FHIR, etc.) only needs to implement this
interface and register itself in ``factory.py``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass(frozen=True)
class MCPFileEvent:
    """Emitted when a new file is detected in the monitored source."""

    filename: str
    uri: str            # canonical identifier (path or blob URI)
    size_bytes: int = 0


class MCPServer(abc.ABC):
    """Protocol-agnostic file-source interface."""

    @abc.abstractmethod
    async def list_files(self) -> list[MCPFileEvent]:
        """Return all files currently available in the source."""

    @abc.abstractmethod
    async def watch(self, poll_seconds: float = 5.0) -> AsyncIterator[MCPFileEvent]:
        """Yield new files as they appear (long-running generator)."""
        ...  # pragma: no cover

    @abc.abstractmethod
    async def read_bytes(self, uri: str) -> bytes:
        """Download / read the raw bytes of a file."""

    @abc.abstractmethod
    async def move_to_processed(self, uri: str) -> str:
        """Move a file to a 'processed' location; return new URI."""

    async def healthcheck(self) -> bool:
        """Return ``True`` if the backend is reachable."""
        return True
