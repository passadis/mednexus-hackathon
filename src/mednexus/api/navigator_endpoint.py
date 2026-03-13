"""Clinical Navigator – read-only case retrieval assistant for staff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from agent_framework import Agent, FunctionTool, Message

from mednexus.config import settings
from mednexus.models.clinical_context import ClinicalContext, Episode
from mednexus.observability import mark_span_failure, start_span
from mednexus.services.cosmos_client import get_cosmos_manager
from mednexus.services.llm_client import create_agent_framework_chat_client
from mednexus.services.search_client import search_documents

logger = structlog.get_logger()

_SYSTEM_PROMPT = """\
You are the MedNexus Clinical Navigator, a read-only staff assistant for case retrieval.

Your job is to help staff find, summarize, and open existing cases across the MedNexus system.

You have access to tools for:
- listing recent cases
- searching cases by topic
- finding multi-episode cases
- getting a patient case summary
- opening a case in the UI

Rules:
- Be concise, factual, and operational.
- Prefer tools over guessing.
- Do not invent findings, timestamps, or case relationships.
- You are read-only. Never imply that you changed records or clinical decisions.
- If the user mentions a specific patient ID such as P145, always scope retrieval results to that patient unless they explicitly ask to compare across patients.
- When the user asks to open a case, call open_case.
- For questions like "today's X-rays", use list_recent_cases with date_scope="today" and modality="radiology_image".
- For broad concepts like injuries, respiratory issues, or elbow pain, use search_cases_by_topic.
- Keep replies plain text, not markdown-heavy formatting.
"""


def _all_findings(ctx: ClinicalContext) -> list[Any]:
    findings: list[Any] = []
    for ep in ctx.episodes:
        findings.extend(ep.findings)
    findings.extend(ctx.findings)
    return findings


def _latest_synthesis(ctx: ClinicalContext) -> Any | None:
    for ep in reversed(ctx.episodes):
        if ep.synthesis is not None:
            return ep.synthesis
    return ctx.synthesis


def _iter_episodes(ctx: ClinicalContext) -> list[Episode]:
    if ctx.episodes:
        return list(ctx.episodes)
    legacy = ctx.ensure_active_episode()
    return [legacy]


def _episode_modalities(ep: Episode) -> list[str]:
    values = sorted({finding.modality.value for finding in ep.findings})
    return values


def _episode_thumbnail_url(ep: Episode) -> str:
    for uri in ep.ingested_files:
        filename = uri.split("/")[-1]
        lower = filename.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".bmp")):
            return f"/api/images/{filename}"
    return ""


def _latest_finding_summary(ep: Episode) -> str:
    if not ep.findings:
        return ""
    return ep.findings[-1].summary[:180]


def _match_date_scope(when: datetime, date_scope: str) -> bool:
    now = datetime.now(timezone.utc)
    scope = (date_scope or "all").lower()
    if scope == "today":
        return when.date() == now.date()
    if scope in {"last_7_days", "week"}:
        return when >= now - timedelta(days=7)
    return True


def _status_matches(ep: Episode, status: str | None) -> bool:
    if not status:
        return True

    normalized = status.strip().lower()
    episode_status = ep.status.value.lower()

    if normalized in {"completed", "complete"}:
        return episode_status in {"synthesis_complete", "approved"}

    if normalized == "latest":
        return ep.synthesis is not None

    return episode_status == normalized


def _modality_matches(ep: Episode, modality: str | None) -> bool:
    if not modality:
        return True

    normalized = modality.strip().lower()
    modalities = _episode_modalities(ep)

    if normalized == "synthesis":
        return ep.synthesis is not None

    if normalized in {"xray", "x-ray", "radiology", "image"}:
        return "radiology_image" in modalities

    return normalized in modalities


async def _exec_list_recent_cases(
    date_scope: str = "today",
    modality: str | None = None,
    status: str | None = None,
    patient_id: str | None = None,
    top: int = 12,
) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    contexts = await cosmos.list_contexts(limit=300)
    items: list[dict[str, Any]] = []
    scoped_patient = patient_id.upper() if patient_id else None

    for ctx in contexts:
        if scoped_patient and ctx.patient.patient_id.upper() != scoped_patient:
            continue
        for ep in _iter_episodes(ctx):
            ep_time = ep.updated_at or ep.created_at
            if not _match_date_scope(ep_time, date_scope):
                continue
            if not _status_matches(ep, status):
                continue
            if not _modality_matches(ep, modality):
                continue
            modalities = _episode_modalities(ep)

            items.append(
                {
                    "patient_id": ctx.patient.patient_id,
                    "name": ctx.patient.name or "(unnamed)",
                    "episode_id": ep.episode_id,
                    "episode_label": ep.label,
                    "status": ep.status.value,
                    "modalities": modalities,
                    "findings_count": len(ep.findings),
                    "has_synthesis": ep.synthesis is not None,
                    "updated_at": ep_time.isoformat(),
                    "summary": _latest_finding_summary(ep),
                    "thumbnail_url": _episode_thumbnail_url(ep),
                }
            )

    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return {
        "count": len(items[:top]),
        "cases": items[:top],
    }


async def _exec_search_cases_by_topic(query: str, top: int = 8) -> dict[str, Any]:
    return await _exec_search_cases_by_topic_for_patient(query=query, patient_id=None, top=top)


async def _exec_search_cases_by_topic_for_patient(
    query: str,
    patient_id: str | None = None,
    top: int = 8,
) -> dict[str, Any]:
    filter_expr = f"patient_id eq '{patient_id.upper()}'" if patient_id else ""
    results = await search_documents(
        query,
        filter_expr=filter_expr,
        top=max(top * 2, 10),
        select=["id", "patient_id", "content_type", "analysis_summary", "content", "source_agent"],
    )
    aggregated: dict[str, dict[str, Any]] = {}
    for doc in results:
        patient_id = doc.get("patient_id", "")
        if not patient_id or patient_id in aggregated:
            continue
        aggregated[patient_id] = {
            "patient_id": patient_id,
            "content_type": doc.get("content_type", ""),
            "source_agent": doc.get("source_agent", ""),
            "score": round(doc.get("@search.score", 0), 3),
            "summary": (doc.get("analysis_summary") or doc.get("content", ""))[:240],
        }
        if len(aggregated) >= top:
            break

    return {
        "query": query,
        "count": len(aggregated),
        "hits": list(aggregated.values()),
    }


async def _exec_find_multi_episode_cases(min_episodes: int = 2, top: int = 10) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    contexts = await cosmos.list_contexts(limit=300)
    items: list[dict[str, Any]] = []
    for ctx in contexts:
        if len(ctx.episodes) < min_episodes:
            continue
        items.append(
            {
                "patient_id": ctx.patient.patient_id,
                "name": ctx.patient.name or "(unnamed)",
                "episodes": len(ctx.episodes),
                "status": ctx.status.value,
                "updated_at": ctx.updated_at.isoformat(),
                "summary": _latest_synthesis(ctx).summary[:180] if _latest_synthesis(ctx) else "",
            }
        )
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return {
        "count": len(items[:top]),
        "cases": items[:top],
    }


async def _exec_get_case_summary(patient_id: str) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id.upper())
    if ctx is None:
        return {"error": f"Patient {patient_id} not found"}

    active_episode = ctx.get_active_episode()
    latest = _latest_synthesis(ctx)
    return {
        "patient_id": ctx.patient.patient_id,
        "name": ctx.patient.name or "(unnamed)",
        "status": ctx.status.value,
        "episodes": len(ctx.episodes),
        "active_episode": active_episode.label if active_episode else None,
        "findings_count": len(_all_findings(ctx)),
        "latest_synthesis": latest.summary[:280] if latest else "",
        "latest_findings": [
            {
                "modality": finding.modality.value,
                "summary": finding.summary[:180],
                "source_agent": finding.source_agent,
            }
            for finding in _all_findings(ctx)[-3:]
        ],
        "thumbnail_url": _episode_thumbnail_url(active_episode) if active_episode else "",
    }


def _build_navigator_tools(
    ui_action_ref: dict[str, Any],
    results_ref: dict[str, Any],
) -> list[FunctionTool]:
    async def list_recent_cases(
        date_scope: str = "today",
        modality: str | None = None,
        status: str | None = None,
        patient_id: str | None = None,
        top: int = 12,
    ) -> dict[str, Any]:
        logger.info(
            "navigator_tool_call",
            tool="list_recent_cases",
            args={
                "date_scope": date_scope,
                "modality": modality,
                "status": status,
                "patient_id": patient_id,
                "top": top,
            },
        )
        result = await _exec_list_recent_cases(
            date_scope=date_scope,
            modality=modality,
            status=status,
            patient_id=patient_id,
            top=top,
        )
        results_ref.clear()
        results_ref.update({"kind": "cases", "items": result.get("cases", [])})
        return result

    async def search_cases_by_topic(query: str, patient_id: str | None = None, top: int = 8) -> dict[str, Any]:
        logger.info(
            "navigator_tool_call",
            tool="search_cases_by_topic",
            args={"query": query, "patient_id": patient_id, "top": top},
        )
        result = await _exec_search_cases_by_topic_for_patient(query=query, patient_id=patient_id, top=top)
        results_ref.clear()
        results_ref.update({"kind": "search_hits", "items": result.get("hits", [])})
        return result

    async def find_multi_episode_cases(min_episodes: int = 2, top: int = 10) -> dict[str, Any]:
        logger.info(
            "navigator_tool_call",
            tool="find_multi_episode_cases",
            args={"min_episodes": min_episodes, "top": top},
        )
        result = await _exec_find_multi_episode_cases(min_episodes=min_episodes, top=top)
        results_ref.clear()
        results_ref.update({"kind": "cases", "items": result.get("cases", [])})
        return result

    async def get_case_summary(patient_id: str) -> dict[str, Any]:
        logger.info("navigator_tool_call", tool="get_case_summary", args={"patient_id": patient_id})
        result = await _exec_get_case_summary(patient_id)
        if not result.get("error"):
            results_ref.clear()
            results_ref.update({"kind": "case_summary", "items": [result]})
        return result

    async def open_case(patient_id: str) -> dict[str, Any]:
        logger.info("navigator_tool_call", tool="open_case", args={"patient_id": patient_id})
        summary = await _exec_get_case_summary(patient_id)
        if summary.get("error"):
            return summary
        ui_action_ref.clear()
        ui_action_ref.update({"type": "navigate", "patient_id": patient_id.upper()})
        results_ref.clear()
        results_ref.update({"kind": "case_summary", "items": [summary]})
        return {"action": "navigate", "patient_id": patient_id.upper()}

    return [
        FunctionTool(
            name="list_recent_cases",
            description="List recent cases by date scope, modality, and status.",
            func=list_recent_cases,
        ),
        FunctionTool(
            name="search_cases_by_topic",
            description="Search cases by clinical topic such as injuries, respiratory findings, elbow pain, or fractures.",
            func=search_cases_by_topic,
        ),
        FunctionTool(
            name="find_multi_episode_cases",
            description="Find patients who have multiple episodes of care.",
            func=find_multi_episode_cases,
        ),
        FunctionTool(
            name="get_case_summary",
            description="Get a compact summary for a patient case by patient ID.",
            func=get_case_summary,
        ),
        FunctionTool(
            name="open_case",
            description="Open a patient case in the UI by patient ID.",
            func=open_case,
        ),
    ]


async def handle_clinical_navigator_chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Process a Clinical Navigator chat turn."""
    latest_user_message = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    ).strip()

    with start_span(
        "clinical_navigator.handle_turn",
        tracer_name="navigator",
        attributes={
            "mednexus.message_count": len(messages),
            "mednexus.latest_user_message": latest_user_message[:200],
        },
    ) as span:
        try:
            ui_action_ref: dict[str, Any] = {}
            results_ref: dict[str, Any] = {}
            agent = Agent(
                client=create_agent_framework_chat_client(),
                name="MedNexus Clinical Navigator",
                instructions=_SYSTEM_PROMPT,
                tools=_build_navigator_tools(ui_action_ref, results_ref),
            )
            session = agent.create_session()
            agent_messages = [
                Message(role=msg["role"], text=msg["content"])
                for msg in messages
                if msg.get("role") in {"user", "assistant"}
            ]

            logger.info(
                "clinical_navigator_request",
                deployment=settings.azure_openai_deployment,
                managed_identity=settings.use_managed_identity,
                runtime="microsoft_agent_framework",
            )
            if span is not None:
                span.set_attribute("mednexus.ai.deployment", settings.azure_openai_deployment)

            response = await agent.run(agent_messages, session=session)
            if span is not None:
                span.set_attribute("mednexus.navigator.results_kind", results_ref.get("kind", "none"))

            return {
                "reply": response.text or "",
                "action": ui_action_ref or None,
                "results": results_ref or None,
            }
        except Exception as exc:
            mark_span_failure(span, exc)
            logger.exception("clinical_navigator_failed")
            return {
                "reply": "The Clinical Navigator is temporarily unavailable. Please try again in a moment.",
                "action": None,
                "results": None,
            }
