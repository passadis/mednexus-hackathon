"""Patient Portal – JWT share, context retrieval, text chat, and voice proxy.

This module provides four capabilities:
  1. Share: Doctor generates a signed JWT link for a specific approved episode.
  2. Context: Patient opens the link and sees a plain-language summary.
  3. Chat:   Patient can ask questions about their episode via text.
  4. Voice:  Real-time voice assistant via Azure OpenAI Realtime proxy.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt
import structlog
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from openai import AsyncAzureOpenAI
from pydantic import BaseModel as _PydBaseModel

from mednexus.config import settings
from mednexus.services.cosmos_client import get_cosmos_manager

logger = structlog.get_logger()

router = APIRouter()

# ── Helpers ──────────────────────────────────────────────────


def _create_portal_token(patient_id: str, episode_id: str) -> str:
    """Create a signed JWT for portal access."""
    payload = {
        "sub": patient_id,
        "eid": episode_id,
        "iss": "mednexus",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.portal_jwt_expiry_hours),
    }
    return jwt.encode(payload, settings.portal_jwt_secret, algorithm="HS256")


def _decode_portal_token(token: str) -> dict[str, Any]:
    """Validate and decode a portal JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.portal_jwt_secret, algorithms=["HS256"], issuer="mednexus")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Portal link has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid portal token")


async def _get_episode_data(token: str) -> tuple[Any, Any]:
    """Decode token and fetch episode + context from Cosmos."""
    claims = _decode_portal_token(token)
    patient_id = claims["sub"]
    episode_id = claims["eid"]

    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, "Patient not found")

    ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None)
    if ep is None:
        raise HTTPException(404, "Episode not found")

    return ctx, ep


async def _rewrite_for_patient(synthesis_summary: str, findings_text: str) -> str:
    """Use GPT-4o to rewrite a clinical synthesis in plain language."""
    if not synthesis_summary:
        return "No clinical summary is available for this visit yet."

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )
    resp = await client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a compassionate medical communicator. Rewrite the following "
                    "clinical synthesis in plain, friendly language that a patient with no "
                    "medical background can understand. Use short sentences. Avoid jargon — "
                    "if you must use a medical term, define it in parentheses. Keep it concise "
                    "(3-5 paragraphs). Start with a warm greeting like 'Here is a summary of "
                    "your recent visit'. End with a gentle reminder to discuss any questions "
                    "with their doctor."
                ),
            },
            {
                "role": "user",
                "content": f"Clinical Synthesis:\n{synthesis_summary}\n\nFindings:\n{findings_text}",
            },
        ],
        temperature=0.4,
        max_tokens=800,
    )
    return resp.choices[0].message.content or synthesis_summary


# ── Request Models ───────────────────────────────────────────


class _PortalChatMessage(_PydBaseModel):
    role: str
    content: str


class _PortalChatRequest(_PydBaseModel):
    messages: list[_PortalChatMessage]


# ── Endpoints ────────────────────────────────────────────────


@router.post("/api/patients/{patient_id}/episodes/{episode_id}/share")
async def share_episode(patient_id: str, episode_id: str) -> dict[str, Any]:
    """Generate a signed portal link for an approved episode."""
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        raise HTTPException(404, "Patient not found")

    ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None)
    if ep is None:
        raise HTTPException(404, "Episode not found")

    if not ep.approved_by:
        raise HTTPException(409, "Cannot share — episode has not been approved by a physician.")

    token = _create_portal_token(patient_id, episode_id)
    return {
        "token": token,
        "patient_id": patient_id,
        "episode_id": episode_id,
        "expires_hours": settings.portal_jwt_expiry_hours,
    }


@router.get("/api/portal/context")
async def portal_context(token: str = Query(...)) -> dict[str, Any]:
    """Retrieve patient-friendly episode context for the portal view."""
    ctx, ep = await _get_episode_data(token)

    # Build findings text for the rewriter
    findings_text = "\n".join(
        f"- [{f.modality}] {f.summary} (confidence: {f.confidence:.0%})"
        for f in ep.findings
    )

    synthesis_summary = ep.synthesis.summary if ep.synthesis else ""
    plain_summary = await _rewrite_for_patient(synthesis_summary, findings_text)

    recommendations = ep.synthesis.recommendations if ep.synthesis else []

    return {
        "patient_name": ctx.patient.name or ctx.patient.patient_id,
        "episode_label": ep.label,
        "episode_date": ep.created_at,
        "status": ep.status,
        "plain_summary": plain_summary,
        "recommendations": recommendations,
        "finding_count": len(ep.findings),
        "approved_by": ep.approved_by,
        "approved_at": ep.approved_at,
    }


@router.post("/api/portal/chat")
async def portal_chat(body: _PortalChatRequest, token: str = Query(...)) -> dict[str, Any]:
    """Patient text chat scoped to a single episode."""
    ctx, ep = await _get_episode_data(token)

    findings_text = "\n".join(
        f"- [{f.modality}] {f.summary}" for f in ep.findings
    )
    synthesis_text = ep.synthesis.summary if ep.synthesis else "No synthesis available."
    recs_text = "\n".join(f"- {r}" for r in (ep.synthesis.recommendations if ep.synthesis else []))

    system_prompt = (
        "You are a friendly, compassionate patient assistant for MedNexus. "
        "You help the patient understand their clinical results from a recent visit.\n\n"
        f"Patient: {ctx.patient.name or ctx.patient.patient_id}\n"
        f"Episode: {ep.label}\n\n"
        f"Clinical Findings:\n{findings_text}\n\n"
        f"Synthesis Summary:\n{synthesis_text}\n\n"
        f"Recommendations:\n{recs_text}\n\n"
        "Guidelines:\n"
        "- Explain medical terms in simple language.\n"
        "- Be warm and supportive.\n"
        "- If the patient asks something outside the scope of this visit's data, "
        "gently redirect them to ask their doctor.\n"
        "- NEVER invent findings or diagnoses not in the data above.\n"
        "- Keep answers concise (2-4 sentences).\n"
        "- Use plain text only, no markdown formatting."
    )

    messages = [{"role": "system", "content": system_prompt}]
    for m in body.messages:
        if m.role in ("user", "assistant"):
            messages.append({"role": m.role, "content": m.content})

    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )
    resp = await client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=messages,
        temperature=0.5,
        max_tokens=500,
    )
    reply = resp.choices[0].message.content or ""
    return {"role": "assistant", "content": reply}


# ── Voice WebSocket Proxy (Azure OpenAI Realtime) ───────────


@router.websocket("/ws/portal/voice")
async def portal_voice(ws: WebSocket, token: str = Query(...)) -> None:
    """Bidirectional WebSocket proxy to Azure OpenAI Realtime API.

    1. Validates the portal JWT.
    2. Fetches episode context from Cosmos.
    3. Opens upstream WebSocket to Azure OpenAI Realtime.
    4. Injects a system prompt with episode data.
    5. Proxies all messages between client and Azure.
    """
    # Validate token before accepting
    try:
        claims = _decode_portal_token(token)
    except HTTPException:
        await ws.close(code=4001, reason="Invalid token")
        return

    await ws.accept()

    patient_id = claims["sub"]
    episode_id = claims["eid"]

    # Fetch episode context
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id)
    if ctx is None:
        await ws.close(code=4004, reason="Patient not found")
        return

    ep = next((e for e in ctx.episodes if e.episode_id == episode_id), None)
    if ep is None:
        await ws.close(code=4004, reason="Episode not found")
        return

    # Build system prompt for the voice assistant
    findings_text = "\n".join(f"- {f.summary}" for f in ep.findings)
    synthesis_text = ep.synthesis.summary if ep.synthesis else "No synthesis yet."
    recs_text = "\n".join(f"- {r}" for r in (ep.synthesis.recommendations if ep.synthesis else []))

    system_instruction = (
        "You are a friendly, compassionate patient voice assistant for MedNexus. "
        "You help the patient understand their clinical results from a recent visit. "
        f"Patient: {ctx.patient.name or ctx.patient.patient_id}. "
        f"Episode: {ep.label}. "
        f"Findings: {findings_text} "
        f"Summary: {synthesis_text} "
        f"Recommendations: {recs_text} "
        "Speak in short, clear sentences. Avoid medical jargon. "
        "If the patient asks something outside the scope of this visit, "
        "gently suggest they ask their doctor. "
        "Be warm, supportive, and concise."
    )

    # Connect to Azure OpenAI Realtime
    endpoint = settings.azure_openai_realtime_endpoint.rstrip("/")
    deploy = settings.azure_openai_realtime_deployment
    ws_url = f"wss://{endpoint.replace('https://', '').replace('http://', '')}/openai/realtime?api-version=2025-04-01-preview&deployment={deploy}"

    import websockets

    try:
        extra_headers = {"api-key": settings.azure_openai_realtime_key}
        async with websockets.connect(ws_url, additional_headers=extra_headers) as upstream:
            # Send session config with system instructions
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": system_instruction,
                    "voice": "alloy",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                    },
                },
            }
            await upstream.send(json.dumps(session_update))

            # Bidirectional proxy
            async def client_to_upstream():
                try:
                    while True:
                        data = await ws.receive_text()
                        await upstream.send(data)
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client():
                try:
                    async for message in upstream:
                        if isinstance(message, str):
                            await ws.send_text(message)
                        else:
                            await ws.send_bytes(message)
                except Exception:
                    pass

            # Run both directions concurrently
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_upstream()),
                    asyncio.create_task(upstream_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

    except Exception as exc:
        logger.error("realtime_proxy_error", error=str(exc))
        try:
            await ws.close(code=4500, reason="Voice service unavailable")
        except Exception:
            pass
