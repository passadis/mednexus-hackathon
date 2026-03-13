"""Bootstrap the MedNexus Azure AI Search index from azd-provided environment."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def _add_src_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


async def _main() -> None:
    _add_src_to_path()

    from mednexus.services.search_index import ensure_search_index

    await ensure_search_index()
    print("Azure AI Search index bootstrap completed.")


if __name__ == "__main__":
    asyncio.run(_main())
