"""Patient Historian Agent – performs RAG via Azure AI Search.

Responsibilities:
  1. Accept a patient_id and optional file (PDF / audio transcript).
  2. If a PDF is supplied, extract text and index it.
  3. If audio is supplied, transcribe via Whisper and index with timestamps.
  4. Query Azure AI Search for historical context matching the patient.
  5. Return a structured summary of the patient's clinical history.

This agent handles three data types for the vector pipeline:
  - Clinical text (structured PDFs, doctor notes)
  - X-ray analysis descriptions (Vision Specialist output)
  - Audio transcripts (Azure OpenAI Whisper with timestamped segments)
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from mednexus.agents.base import BaseAgent
from mednexus.models.agent_messages import AgentRole, TaskAssignment, TaskResult


class PatientHistorianAgent(BaseAgent):
    """Retrieves and synthesises patient history using RAG."""

    role = AgentRole.PATIENT_HISTORIAN

    _SYSTEM_PROMPT = (
        "You are a clinical informaticist. You review patient records retrieved "
        "from the hospital's knowledge base and produce a concise clinical summary.\n\n"
        "Structure your response as JSON with keys:\n"
        "- history_summary: a 2-3 paragraph clinical narrative\n"
        "- key_diagnoses: list of past diagnoses\n"
        "- active_medications: list of current medications\n"
        "- relevant_labs: list of notable lab values\n"
        "- risk_factors: list of identified risk factors\n"
        "- transcript_segments: if an audio transcript was provided, include the "
        "  timestamped segments as a list of {start, end, text} objects\n"
        "- confidence: 0.0-1.0"
    )

    async def handle_task(self, assignment: TaskAssignment) -> TaskResult:
        """Process a history lookup / PDF ingestion / audio transcription task."""
        self.log.info("historian_start", patient=assignment.patient_id)

        try:
            # Step 1 – if a file is provided, extract its text
            file_text = ""
            transcript_data: dict[str, Any] | None = None

            if assignment.file_uri:
                if assignment.file_type == "audio":
                    transcript_data = await self._process_audio(
                        assignment.file_uri, assignment.patient_id
                    )
                    file_text = transcript_data.get("full_text", "") if transcript_data else ""
                else:
                    file_text = await self._extract_text(
                        assignment.file_uri, assignment.file_type
                    )
                    # Index text documents to AI Search
                    if file_text:
                        await self._index_to_search(
                            patient_id=assignment.patient_id,
                            content=file_text,
                            content_type=assignment.file_type or "note",
                            source_uri=assignment.file_uri,
                        )

            # Step 2 – RAG: search Azure AI Search for this patient
            search_results = await self._search_patient_history(
                patient_id=assignment.patient_id,
                query=file_text[:500] if file_text else f"clinical history for {assignment.patient_id}",
            )

            # Step 3 – synthesise with LLM
            context = self._build_context(file_text, search_results)
            raw = await self.call_llm(
                system_prompt=self._SYSTEM_PROMPT,
                user_prompt=(
                    f"Patient ID: {assignment.patient_id}\n\n"
                    f"Retrieved Records:\n{context}\n\n"
                    f"Additional instructions: {assignment.instructions}"
                ),
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            try:
                parsed: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                # LLM response may have been truncated — try closing braces
                repaired = raw.rstrip()
                # Close any open string, then close all open braces/brackets
                open_braces = repaired.count("{") - repaired.count("}")
                open_brackets = repaired.count("[") - repaired.count("]")
                if open_braces > 0 or open_brackets > 0:
                    repaired += '"' + "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = {"history_summary": raw, "confidence": 0.5}

            # Merge transcript segments into the structured output
            if transcript_data and transcript_data.get("segments"):
                parsed["transcript_segments"] = transcript_data["segments"]
                parsed["audio_duration"] = transcript_data.get("duration", 0)

            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=True,
                summary=parsed.get("history_summary", "History retrieval complete."),
                structured_output=parsed,
            )

        except Exception as exc:
            self.log.error("historian_error", error=str(exc))
            return TaskResult(
                task_id=assignment.task_id,
                patient_id=assignment.patient_id,
                agent=self.role,
                success=False,
                error_detail=str(exc),
            )

    # ── Audio processing ─────────────────────────────────────

    async def _process_audio(
        self, uri: str, patient_id: str
    ) -> dict[str, Any]:
        """Transcribe audio via Whisper and index the result to AI Search.

        Returns the transcript data dict with full_text, segments, duration.
        """
        from mednexus.mcp import create_mcp_server
        from mednexus.services.speech_client import transcribe_audio

        mcp = create_mcp_server()
        audio_bytes = await mcp.read_bytes(uri)
        result = await transcribe_audio(audio_bytes)

        transcript_dict = result.to_dict()

        # Index the full transcript text to AI Search with embedding
        if result.full_text and not result.full_text.startswith("["):
            await self._index_to_search(
                patient_id=patient_id,
                content=result.full_text,
                content_type="interview",
                source_uri=uri,
                extra_fields={
                    "analysis_summary": (
                        f"Audio transcript ({result.duration:.0f}s, "
                        f"{len(result.segments)} segments). "
                        f"Language: {result.language}"
                    ),
                },
            )

        self.log.info(
            "audio_processed",
            patient=patient_id,
            segments=len(result.segments),
            duration=f"{result.duration:.1f}s",
        )
        return transcript_dict

    # ── Text extraction ──────────────────────────────────────

    async def _extract_text(self, uri: str, file_type: str) -> str:
        """Extract text from a PDF or return raw text content."""
        from mednexus.mcp import create_mcp_server

        mcp = create_mcp_server()
        raw = await mcp.read_bytes(uri)

        if file_type == "pdf":
            return self._pdf_to_text(raw)
        # Default: try decoding as text
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def _pdf_to_text(data: bytes) -> str:
        """Extract text from PDF bytes using PyPDF2."""
        import io
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    # ── AI Search integration ────────────────────────────────

    async def _index_to_search(
        self,
        *,
        patient_id: str,
        content: str,
        content_type: str,
        source_uri: str,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        """Push a document into Azure AI Search (auto-embeds)."""
        from mednexus.services.search_client import index_document

        safe_id = re.sub(r"[^a-zA-Z0-9_=\-]", "_", patient_id)
        doc: dict[str, Any] = {
            "id": f"{safe_id}-{content_type}-{uuid.uuid4().hex[:8]}",
            "patient_id": patient_id,
            "content_type": content_type,
            "source_agent": "patient_historian",
            "content": content[:32000],  # Search field size limit
            "metadata_storage_path": source_uri,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra_fields:
            doc.update(extra_fields)

        await index_document(doc)  # auto_embed=True by default

    async def _search_patient_history(
        self, patient_id: str, query: str
    ) -> list[dict[str, Any]]:
        """Query Azure AI Search with a patient_id filter."""
        from mednexus.services.search_client import search_patient_documents

        return await search_patient_documents(patient_id, query, top=10)

    @staticmethod
    def _build_context(file_text: str, search_results: list[dict[str, Any]]) -> str:
        """Combine file text and search results into a single context string."""
        parts: list[str] = []
        if file_text:
            parts.append(f"=== Ingested Document ===\n{file_text[:3000]}")
        for i, doc in enumerate(search_results, 1):
            content = doc.get("content", doc.get("text", ""))
            parts.append(f"=== Search Result {i} ===\n{content[:1000]}")
        return "\n\n".join(parts) if parts else "No records found."
