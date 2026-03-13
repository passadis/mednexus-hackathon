"""Azure OpenAI Whisper transcription client.

Returns structured transcripts with per-segment timestamps so the
TranscriptCard UI can render clickable, time-aligned text.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import structlog

from mednexus.config import settings

logger = structlog.get_logger()


# ── Data models ──────────────────────────────────────────────


@dataclass
class TranscriptSegment:
    """A single timed segment from Whisper."""

    start: float  # seconds
    end: float
    text: str


@dataclass
class TranscriptResult:
    """Full structured transcript with metadata."""

    full_text: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    language: str = "en"
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_text": self.full_text,
            "segments": [asdict(s) for s in self.segments],
            "language": self.language,
            "duration": self.duration,
        }


# ── Transcription ────────────────────────────────────────────


async def transcribe_audio(audio_bytes: bytes) -> TranscriptResult:
    """Transcribe audio bytes using Azure OpenAI Whisper.

    Uses ``verbose_json`` response format to get per-segment timestamps.
    Returns a ``TranscriptResult`` with the full text and timed segments.
    """
    if not settings.azure_openai_endpoint or (
        not settings.azure_openai_api_key and not settings.use_managed_identity
    ):
        logger.warning("whisper_not_configured")
        return TranscriptResult(
            full_text="[Audio transcription unavailable – OpenAI not configured]"
        )

    try:
        from openai import AsyncAzureOpenAI
        from mednexus.services.llm_client import _azure_ad_token_provider

        if settings.use_managed_identity:
            client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                azure_ad_token_provider=_azure_ad_token_provider(),
                api_version=settings.azure_openai_api_version,
                timeout=30.0,
                max_retries=1,
            )
        else:
            client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                timeout=30.0,
                max_retries=1,
            )

        # Whisper requires a file-like object with a name attribute
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model=settings.azure_openai_whisper_deployment,
                file=audio_file,
                response_format="verbose_json",
                language="en",
                timestamp_granularities=["segment"],
            )

        # Cleanup temp file
        Path(tmp_path).unlink(missing_ok=True)
        await client.close()

        # Parse the verbose_json response into structured segments
        segments: list[TranscriptSegment] = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                segments.append(
                    TranscriptSegment(
                        start=seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0),
                        end=seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0),
                        text=(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip(),
                    )
                )

        full_text = response.text if hasattr(response, "text") else ""
        duration = response.duration if hasattr(response, "duration") else 0.0

        result = TranscriptResult(
            full_text=full_text,
            segments=segments,
            language="en",
            duration=duration,
        )

        logger.info(
            "whisper_transcribed",
            segments=len(segments),
            duration=f"{duration:.1f}s",
            chars=len(full_text),
        )
        return result

    except Exception as exc:
        logger.error("whisper_error", error=str(exc))
        return TranscriptResult(full_text=f"[Transcription failed: {exc}]")
