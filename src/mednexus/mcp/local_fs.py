"""Local filesystem MCP server – watches a drop-folder on disk."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import AsyncIterator

import aiofiles

from mednexus.mcp.base import MCPFileEvent, MCPServer


class LocalFileSystemMCP(MCPServer):
    """MCP backend that monitors a local directory for new medical files."""

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._processed = self._root / "_processed"
        self._processed.mkdir(exist_ok=True)
        self._seen: set[str] = set()

    # ── interface ────────────────────────────────────────────

    async def list_files(self) -> list[MCPFileEvent]:
        events: list[MCPFileEvent] = []
        for entry in self._root.iterdir():
            if entry.is_file() and not entry.name.startswith("_"):
                events.append(
                    MCPFileEvent(
                        filename=entry.name,
                        uri=str(entry),
                        size_bytes=entry.stat().st_size,
                    )
                )
        return events

    async def watch(self, poll_seconds: float = 5.0) -> AsyncIterator[MCPFileEvent]:
        """Poll the directory and yield *new* files only."""
        while True:
            for entry in self._root.iterdir():
                if entry.is_file() and not entry.name.startswith("_"):
                    key = f"{entry.name}:{entry.stat().st_mtime}"
                    if key not in self._seen:
                        self._seen.add(key)
                        yield MCPFileEvent(
                            filename=entry.name,
                            uri=str(entry),
                            size_bytes=entry.stat().st_size,
                        )
            await asyncio.sleep(poll_seconds)

    async def read_bytes(self, uri: str) -> bytes:
        async with aiofiles.open(uri, "rb") as f:
            return await f.read()

    async def move_to_processed(self, uri: str) -> str:
        src = Path(uri)
        dst = self._processed / src.name
        # Avoid overwrites by appending a hash fragment
        if dst.exists():
            h = hashlib.sha256(src.name.encode()).hexdigest()[:8]
            dst = self._processed / f"{src.stem}_{h}{src.suffix}"
        shutil.move(str(src), str(dst))
        return str(dst)

    def delete_files_by_prefix(self, prefix: str) -> int:
        """Delete all files whose name starts with *prefix* (incl. _processed/)."""
        count = 0
        for folder in (self._root, self._processed):
            if not folder.exists():
                continue
            for entry in folder.iterdir():
                if entry.is_file() and entry.name.upper().startswith(prefix.upper()):
                    entry.unlink(missing_ok=True)
                    count += 1
        return count

    def delete_files(self, filenames: list[str]) -> int:
        """Delete specific files by name from root and _processed."""
        count = 0
        for name in filenames:
            for folder in (self._root, self._processed):
                path = folder / name
                if path.exists():
                    path.unlink()
                    count += 1
        return count

    async def healthcheck(self) -> bool:
        return self._root.exists()
