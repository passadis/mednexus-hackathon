"""MedNexus API – FastAPI backend.

Provides REST + WebSocket endpoints for the MedNexus Command Center UI:
  - Patient context CRUD
  - File upload & agent dispatch
  - Agent Chatter WebSocket (live A2A stream)
  - Health check & system status
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from mednexus.a2a import get_a2a_bus
from mednexus.agents.clinical_sorter import ClinicalSorterAgent
from mednexus.agents.diagnostic_synthesis import DiagnosticSynthesisAgent
from mednexus.agents.orchestrator import OrchestratorAgent
from mednexus.agents.patient_historian import PatientHistorianAgent
from mednexus.agents.vision_specialist import VisionSpecialistAgent
from mednexus.api.portal_endpoints import router as portal_router
from mednexus.config import settings
from mednexus.models.clinical_context import ClinicalContext
from mednexus.services.cosmos_client import get_cosmos_manager

logger = structlog.get_logger()


# ── Lifespan ─────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """Startup: register all agents on the A2A bus.  Shutdown: cleanup."""
    bus = get_a2a_bus()

    # Create and register all agents
    orchestrator = OrchestratorAgent()
    sorter = ClinicalSorterAgent()
    vision = VisionSpecialistAgent()
    historian = PatientHistorianAgent()
    synthesis = DiagnosticSynthesisAgent()

    for agent in [orchestrator, sorter, vision, historian, synthesis]:
        bus.register(agent)

    # Start specialist agents' event loops in background
    tasks = []
    for agent in [orchestrator, sorter, vision, historian, synthesis]:
        tasks.append(asyncio.create_task(agent.start()))

    # Store refs for route handlers
    app.state.orchestrator = orchestrator
    app.state.bus = bus

    logger.info("mednexus_started", agents=bus.registered_agents)
    yield

    # Shutdown
    for t in tasks:
        t.cancel()
    cosmos = get_cosmos_manager()
    await cosmos.close()
    logger.info("mednexus_shutdown")


# ── App factory ──────────────────────────────────────────────

app = FastAPI(
    title="MedNexus API",
    version="0.1.0",
    description="Multi-Agent Healthcare Orchestration Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Portal routes (share, context, chat, voice) ─────────────
app.include_router(portal_router)


# ── Request / Response Models ────────────────────────────────

from pydantic import BaseModel as _PydBaseModel  # noqa: E402


class _ApprovalRequest(_PydBaseModel):
    approved_by: str
    notes: str = ""
    episode_id: str | None = None


class _ChatMessage(_PydBaseModel):
    role: str
    content: str


class _ChatRequest(_PydBaseModel):
    messages: list[_ChatMessage]


class _EpisodeCreateRequest(_PydBaseModel):
    label: str = ""


# ── Health ───────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, Any]:
    bus = get_a2a_bus()
    return {
        "status": "healthy",
        "agents": bus.registered_agents,
        "message_count": bus.message_count,
    }


# ── Patient Context ─────────────────────────────────────────


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str) -> dict[str, Any]:
    """Retrieve a patient's Clinical Context, auto-creating if new."""
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        ctx = await cosmos.create_context(patient_id)
    return ctx.to_cosmos_doc()


@app.get("/api/patients")
async def list_patients(limit: int = Query(default=50, le=200)) -> list[dict[str, Any]]:
    """List all patient contexts."""
    cosmos = get_cosmos_manager()
    contexts = await cosmos.list_contexts(limit=limit)
    return [c.to_cosmos_doc() for c in contexts]


@app.post("/api/patients/{patient_id}")
async def create_patient(patient_id: str, name: str = "") -> dict[str, Any]:
    """Create a new patient context."""
    cosmos = get_cosmos_manager()
    existing = await cosmos.get_context(patient_id)
    if existing:
        raise HTTPException(409, f"Patient {patient_id} already exists")
    ctx = await cosmos.create_context(patient_id, name)
    return ctx.to_cosmos_doc()


# ── Episode Management ───────────────────────────────────────


@app.get("/api/patients/{patient_id}/episodes")
async def list_episodes(patient_id: str) -> list[dict[str, Any]]:
    """Return all episodes for a patient, most-recent first."""
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, f"Patient {patient_id} not found")
    return [ep.model_dump(mode="json") for ep in reversed(ctx.episodes)]


@app.post("/api/patients/{patient_id}/episodes")
async def create_episode(patient_id: str, body: _EpisodeCreateRequest | None = None) -> dict[str, Any]:
    """Create a new episode for a patient and set it as active.

    Body is optional — if omitted an auto-labeled episode is created.
    """
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, f"Patient {patient_id} not found")

    label = (body.label if body and body.label else "")
    ep = ctx.create_episode(label=label)
    await cosmos.upsert_context(ctx)

    logger.info("episode_created", patient_id=patient_id, episode_id=ep.episode_id, label=ep.label)
    return ep.model_dump(mode="json")


@app.patch("/api/patients/{patient_id}/episodes/{episode_id}/activate")
async def activate_episode(patient_id: str, episode_id: str) -> dict[str, Any]:
    """Set a specific episode as the active one."""
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, f"Patient {patient_id} not found")

    ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None)
    if ep is None:
        raise HTTPException(404, f"Episode {episode_id} not found")

    ctx.active_episode_id = ep.episode_id
    await cosmos.upsert_context(ctx)
    return {"active_episode_id": ep.episode_id, "label": ep.label}


# ── File Upload & Agent Dispatch ─────────────────────────────


@app.post("/api/patients/{patient_id}/upload")
async def upload_file(
    patient_id: str,
    file: UploadFile = File(...),
    episode_id: str | None = Query(default=None, description="Target episode ID (creates new episode if omitted)"),
) -> dict[str, Any]:
    """Upload a medical file and trigger the agent pipeline.

    Optionally specify ``episode_id`` to route the file to a specific
    episode.  If omitted the active episode is used (or a new one is
    created automatically).
    """
    from pathlib import Path

    if not file.filename:
        raise HTTPException(400, "Filename is required")

    # Prefix with patient_id if not already present
    filename = file.filename
    if not filename.upper().startswith(patient_id.upper()):
        filename = f"{patient_id}_{filename}"

    content = await file.read()

    # Save to local drop-folder (always, for backup)
    drop_folder = Path(settings.mcp_drop_folder)
    drop_folder.mkdir(parents=True, exist_ok=True)
    dest = drop_folder / filename
    dest.write_bytes(content)

    # If Azure Blob MCP is configured, also upload to blob so agents can read
    file_uri = str(dest)
    if settings.azure_storage_connection_string:
        from azure.storage.blob.aio import ContainerClient

        async with ContainerClient.from_connection_string(
            settings.azure_storage_connection_string,
            settings.azure_storage_container,
        ) as container:
            await container.upload_blob(filename, content, overwrite=True)
        file_uri = f"az://{settings.azure_storage_container}/{filename}"

    # Classify the file
    sorter = ClinicalSorterAgent()
    med_file = await sorter.classify_file(filename, file_uri)
    med_file.patient_id = patient_id

    # Get or create context
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        ctx = await cosmos.create_context(patient_id)

    # Dispatch to orchestrator (episode-aware)
    orchestrator: OrchestratorAgent = app.state.orchestrator
    task_id = await orchestrator.ingest_file(med_file, ctx, episode_id=episode_id)
    await cosmos.upsert_context(ctx)

    active_ep = ctx.get_active_episode()
    return {
        "task_id": task_id,
        "file_type": med_file.file_type.value,
        "patient_id": patient_id,
        "episode_id": active_ep.episode_id if active_ep else None,
        "status": ctx.status.value,
    }


# ── Image Proxy ──────────────────────────────────────────────


@app.get("/api/images/{filename}")
async def serve_image(filename: str):
    """Serve a medical image from Azure Blob Storage (or local fallback).

    The UI calls this to display X-ray thumbnails without needing a
    public blob URL or SAS token.
    """
    from pathlib import Path

    from fastapi.responses import Response

    content_type = "image/png" if filename.lower().endswith(".png") else "application/octet-stream"

    # Try Azure Blob first
    if settings.azure_storage_connection_string:
        try:
            from azure.storage.blob.aio import ContainerClient

            async with ContainerClient.from_connection_string(
                settings.azure_storage_connection_string,
                settings.azure_storage_container,
            ) as container:
                blob = await container.download_blob(filename)
                data = await blob.readall()
                return Response(content=data, media_type=content_type)
        except Exception:
            pass  # fall through to local

    # Local fallback
    local_path = Path(settings.mcp_drop_folder) / filename
    if local_path.exists():
        return Response(content=local_path.read_bytes(), media_type=content_type)

    raise HTTPException(404, f"Image {filename} not found")


# ── Agent Chatter WebSocket ─────────────────────────────────


@app.websocket("/ws/chatter")
async def agent_chatter(ws: WebSocket) -> None:
    """Live A2A message stream for the Command Center's Agent Chatter pane."""
    await ws.accept()
    bus: Any = get_a2a_bus()

    async def send_event(event: dict[str, Any]) -> None:
        await ws.send_json(event)

    bus.add_observer(send_event)
    logger.info("ws_client_connected")

    try:
        while True:
            # Keep connection alive; client can also send commands
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"event": "pong"})
    except WebSocketDisconnect:
        bus.remove_observer(send_event)
        logger.info("ws_client_disconnected")


# ── Agent Message History ────────────────────────────────────


@app.get("/api/chatter/history")
async def chatter_history(limit: int = Query(default=50, le=200)) -> list[dict[str, Any]]:
    """Return recent A2A messages for late-joining clients."""
    bus = get_a2a_bus()
    return bus.get_recent_messages(limit)


# ── Human-in-the-Loop: MD Approval (Phase 3) ────────────────


@app.post("/api/patients/{patient_id}/approve")
async def approve_synthesis(patient_id: str, body: _ApprovalRequest) -> dict[str, Any]:
    """MD sign-off on a Synthesis Report (Human-in-the-Loop).

    If ``episode_id`` is provided the approval targets that specific
    episode; otherwise it falls back to the active episode.
    """
    from datetime import datetime, timezone
    from mednexus.models.clinical_context import ContextStatus

    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, f"Patient {patient_id} not found")

    # Resolve episode
    ep = None
    if body.episode_id:
        ep = next((e for e in ctx.episodes if e.episode_id == body.episode_id), None)
    if ep is None:
        ep = ctx.get_active_episode()

    # Episode-level approval
    if ep:
        if ep.synthesis is None:
            raise HTTPException(409, "Cannot approve – no synthesis report for this episode.")
        if ep.approved_by:
            raise HTTPException(409, "Episode already approved.")
        ep.approved_by = body.approved_by
        ep.approved_at = datetime.now(timezone.utc)
        ep.status = ContextStatus.APPROVED
        ep.touch()

    # Legacy top-level approval (backward-compat)
    if ctx.synthesis is None and (ep is None or ep.synthesis is None):
        raise HTTPException(409, "Cannot approve – no synthesis report has been generated yet.")

    ctx.status = ContextStatus.APPROVED
    ctx.approved_by = body.approved_by
    ctx.approved_at = datetime.now(timezone.utc)
    ctx.approval_notes = body.notes
    ctx.log_activity(
        agent="human",
        action="md_approval",
        detail=f"[{ep.label if ep else 'global'}] Approved by {body.approved_by}",
    )
    await cosmos.upsert_context(ctx)

    logger.info("synthesis_approved", patient_id=patient_id, approved_by=body.approved_by)
    return {
        "patient_id": patient_id,
        "episode_id": ep.episode_id if ep else None,
        "status": ctx.status.value,
        "approved_by": ctx.approved_by,
        "approved_at": ctx.approved_at.isoformat() if ctx.approved_at else None,
    }


# ── Doctor Chat (Conversational Concierge) ───────────────────


@app.post("/api/chat")
async def doctor_chat(body: _ChatRequest) -> dict[str, Any]:
    """Conversational chat powered by GPT-4o with function calling.

    The physician can ask natural-language questions about patients,
    findings, and synthesis reports.  The agent can also trigger UI
    navigation (e.g. "bring up Emily").
    """
    from mednexus.api.chat_endpoint import handle_doctor_chat

    msgs = [{"role": m.role, "content": m.content} for m in body.messages]
    result = await handle_doctor_chat(msgs)
    return result
