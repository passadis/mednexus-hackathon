"""Doctor Chat – conversational concierge backed by GPT-4o function calling.

The chat endpoint lets an attending physician ask natural-language questions
such as "How many patients do we have?", "Is there an Emily Johnson?", or
"Bring up Emily" and automatically surfaces Cosmos data or triggers patient
navigation in the UI.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from agent_framework import Agent, FunctionTool, Message
from pydantic import BaseModel

from mednexus.config import settings
from mednexus.observability import mark_span_failure, start_span
from mednexus.services.cosmos_client import get_cosmos_manager
from mednexus.services.llm_client import create_agent_framework_chat_client

logger = structlog.get_logger()

_PATIENT_ID_QUERY_RE = re.compile(r"\b(P\d{3,})\b", re.IGNORECASE)
_LOAD_PATIENT_VERBS = ("show", "bring up", "open", "load", "go to", "navigate")
_CASE_QUERY_TERMS = ("case", "summary", "summarize", "what do we know", "tell me about", "overview")

class SearchPatientInput(BaseModel):
    query: str


class LoadPatientInput(BaseModel):
    patient_id: str


class GetFindingsInput(BaseModel):
    patient_id: str
    modality: str | None = None


class GetSynthesisInput(BaseModel):
    patient_id: str


class GetPatientCaseInput(BaseModel):
    patient_id: str


class SearchClinicalDataInput(BaseModel):
    query: str
    patient_id: str | None = None

_SYSTEM_PROMPT = """\
You are the MedNexus Clinical Concierge, an AI assistant embedded in a \
multi-agent healthcare platform.  You help the attending physician navigate \
patient data, review findings, and understand synthesis reports.

You have access to the following tools:
- list_patients: enumerate all patients in the system
- search_patient: fuzzy-search patients by name
- load_patient: navigate the UI to a specific patient
- get_patient_case: retrieve the overall case summary for a patient
- get_findings: retrieve clinical findings for a patient
- get_synthesis: retrieve the diagnostic synthesis report
- search_clinical_data: semantic hybrid search across ALL clinical documents (findings, X-ray reports, transcripts)

Guidelines:
• Be concise and clinical in tone.
• When the user asks to "bring up" or "show" a patient, call load_patient.
• When the user asks for a patient's case, summary, overview, or "what do we know", call get_patient_case.
• When the user asks about findings or X-ray results, call get_findings.
• When the user asks broad clinical questions across patients (e.g. "any lung \
opacity?", "cardiac abnormalities?", "who has abnormal findings?"), use \
search_clinical_data for hybrid semantic search.
• Always prefer querying tools over guessing — use real data.
• After calling load_patient, tell the user you've navigated to that patient.
• list_patients returns patients sorted by most recently UPDATED first. \
Each patient includes "created_at" (when first added) and "updated_at" \
(last modification). Use "created_at" to determine which patient was added \
most recently.

CRITICAL FORMATTING RULES:
• NEVER use Markdown syntax. No **bold**, no *italic*, no # headings, \
no ```code blocks```, no [links](url).
• Use plain text only. For emphasis, use CAPS or quotation marks.
• Use simple bullet points with "•" or "-" (no nested markdown lists).
• Use line breaks for readability.
• Keep responses compact — 2-4 sentences for simple queries.
• For patient lists, use a clean numbered format like:
  1. Emily Johnson (P001) — 2 findings, synthesis complete
  2. Robert Chen (P002) — 3 findings, synthesis complete
"""


# ── Tool Implementations ─────────────────────────────────────


def _all_findings(ctx: Any) -> list[Any]:
    """Collect findings from all episodes + legacy flat list."""
    findings: list[Any] = []
    for ep in ctx.episodes:
        findings.extend(ep.findings)
    findings.extend(ctx.findings)  # legacy fallback
    return findings


def _latest_synthesis(ctx: Any) -> Any | None:
    """Return the most recent synthesis across episodes, or legacy."""
    for ep in reversed(ctx.episodes):
        if ep.synthesis is not None:
            return ep.synthesis
    return ctx.synthesis


async def _exec_list_patients() -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    contexts = await cosmos.list_contexts(limit=50)
    patients = []
    for ctx in contexts:
        all_f = _all_findings(ctx)
        patients.append({
            "patient_id": ctx.patient.patient_id,
            "name": ctx.patient.name or "(unnamed)",
            "status": ctx.status.value,
            "episodes": len(ctx.episodes),
            "findings_count": len(all_f),
            "has_synthesis": _latest_synthesis(ctx) is not None,
            "created_at": ctx.created_at.isoformat(),
            "updated_at": ctx.updated_at.isoformat(),
        })
    return {"count": len(patients), "patients": patients}


async def _exec_search_patient(query: str) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    contexts = await cosmos.list_contexts(limit=200)
    q = query.lower()
    matches = []
    for ctx in contexts:
        name = (ctx.patient.name or "").lower()
        pid = ctx.patient.patient_id.lower()
        if q in name or q in pid:
            matches.append({
                "patient_id": ctx.patient.patient_id,
                "name": ctx.patient.name or "(unnamed)",
                "status": ctx.status.value,
            })
    return {"matches": matches, "count": len(matches)}


async def _exec_load_patient(patient_id: str) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id.upper())
    if ctx is None:
        return {"error": f"Patient {patient_id} not found"}
    all_f = _all_findings(ctx)
    syn = _latest_synthesis(ctx)
    episodes_summary = []
    for ep in ctx.episodes:
        episodes_summary.append({
            "episode_id": ep.episode_id,
            "label": ep.label,
            "status": ep.status.value,
            "findings_count": len(ep.findings),
            "has_synthesis": ep.synthesis is not None,
            "files": [u.split('/').pop() for u in ep.ingested_files],
        })
    return {
        "action": "navigate",
        "patient_id": ctx.patient.patient_id,
        "name": ctx.patient.name or "(unnamed)",
        "status": ctx.status.value,
        "episodes": episodes_summary,
        "findings_count": len(all_f),
        "has_synthesis": syn is not None,
        "created_at": ctx.created_at.isoformat(),
        "updated_at": ctx.updated_at.isoformat(),
    }


async def _exec_get_findings(patient_id: str, modality: str | None = None) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id.upper())
    if ctx is None:
        return {"error": f"Patient {patient_id} not found"}

    findings = _all_findings(ctx)
    if modality:
        findings = [f for f in findings if f.modality.value == modality]

    return {
        "patient_id": ctx.patient.patient_id,
        "findings": [
            {
                "finding_id": f.finding_id,
                "modality": f.modality.value,
                "source_agent": f.source_agent,
                "summary": f.summary,
                "confidence": f.confidence,
                "details": f.details,
            }
            for f in findings
        ],
    }


async def _exec_get_synthesis(patient_id: str) -> dict[str, Any]:
    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id.upper())
    if ctx is None:
        return {"error": f"Patient {patient_id} not found"}

    # Collect per-episode synthesis reports
    episode_reports = []
    for ep in ctx.episodes:
        if ep.synthesis is not None:
            s = ep.synthesis
            episode_reports.append({
                "episode": ep.label,
                "summary": s.summary,
                "cross_modality_notes": s.cross_modality_notes,
                "recommendations": s.recommendations,
                "discrepancies": [
                    {"description": d.description, "severity": d.severity}
                    for d in s.discrepancies
                ],
                "generated_at": s.generated_at.isoformat() if s.generated_at else None,
            })

    # Legacy fallback
    if not episode_reports and ctx.synthesis is not None:
        s = ctx.synthesis
        episode_reports.append({
            "episode": "(legacy)",
            "summary": s.summary,
            "cross_modality_notes": s.cross_modality_notes,
            "recommendations": s.recommendations,
            "discrepancies": [
                {"description": d.description, "severity": d.severity}
                for d in s.discrepancies
            ],
            "generated_at": s.generated_at.isoformat() if s.generated_at else None,
        })

    if not episode_reports:
        return {"patient_id": ctx.patient.patient_id, "synthesis": None, "message": "No synthesis report generated yet."}

    return {
        "patient_id": ctx.patient.patient_id,
        "reports": episode_reports,
    }


async def _exec_get_patient_case(patient_id: str) -> dict[str, Any]:
    """Return a compact patient case view backed by Cosmos and patient-scoped Search."""
    from mednexus.services.search_client import search_patient_documents

    cosmos = get_cosmos_manager()
    ctx = await cosmos.get_context(patient_id.upper())
    if ctx is None:
        return {"error": f"Patient {patient_id} not found"}

    findings = _all_findings(ctx)
    synthesis = await _exec_get_synthesis(patient_id)

    search_hits: list[dict[str, Any]] = []
    try:
        docs = await search_patient_documents(
            patient_id.upper(),
            "clinical summary findings history transcript imaging labs",
            top=5,
        )
        for doc in docs:
            search_hits.append({
                "content_type": doc.get("content_type", ""),
                "source_agent": doc.get("source_agent", ""),
                "summary": (doc.get("analysis_summary") or doc.get("content", ""))[:280],
            })
    except Exception as exc:
        logger.warning("patient_case_search_error", patient_id=patient_id, error=str(exc))

    active_episode = ctx.get_active_episode()
    return {
        "patient_id": ctx.patient.patient_id,
        "name": ctx.patient.name or "(unnamed)",
        "status": ctx.status.value,
        "episodes": len(ctx.episodes),
        "active_episode": active_episode.label if active_episode else None,
        "findings_count": len(findings),
        "latest_findings": [
            {
                "modality": f.modality.value,
                "source_agent": f.source_agent,
                "summary": f.summary,
                "confidence": f.confidence,
            }
            for f in findings[-5:]
        ],
        "synthesis": synthesis.get("reports", []),
        "search_hits": search_hits,
    }


async def _exec_search_clinical_data(query: str, patient_id: str | None = None) -> dict[str, Any]:
    from mednexus.services.search_client import search_documents, search_patient_documents

    try:
        if patient_id:
            results = await search_patient_documents(patient_id.upper(), query, top=8)
        else:
            results = await search_documents(query, top=8)
    except Exception as exc:
        logger.warning("search_clinical_error", error=str(exc))
        return {"error": f"Search failed: {exc}", "results": []}

    hits = []
    for doc in results:
        hits.append({
            "patient_id": doc.get("patient_id", ""),
            "content_type": doc.get("content_type", ""),
            "source_agent": doc.get("source_agent", ""),
            "summary": (doc.get("analysis_summary") or doc.get("content", ""))[:300],
            "score": round(doc.get("@search.score", 0), 3),
        })
    return {"query": query, "results_count": len(hits), "results": hits}


def _build_framework_tools(
    ui_action_ref: dict[str, Any],
) -> list[FunctionTool]:
    async def list_patients() -> dict[str, Any]:
        logger.info("doctor_chat_tool_call", tool="list_patients", args={})
        return await _exec_list_patients()

    async def search_patient(query: str) -> dict[str, Any]:
        logger.info("doctor_chat_tool_call", tool="search_patient", args={"query": query})
        return await _exec_search_patient(query)

    async def load_patient(patient_id: str) -> dict[str, Any]:
        logger.info("doctor_chat_tool_call", tool="load_patient", args={"patient_id": patient_id})
        result = await _exec_load_patient(patient_id)
        if result.get("action") == "navigate":
            ui_action_ref.clear()
            ui_action_ref.update({
                "type": "navigate",
                "patient_id": result["patient_id"],
            })
        return result

    async def get_findings(patient_id: str, modality: str | None = None) -> dict[str, Any]:
        logger.info(
            "doctor_chat_tool_call",
            tool="get_findings",
            args={"patient_id": patient_id, "modality": modality},
        )
        return await _exec_get_findings(patient_id, modality)

    async def get_patient_case(patient_id: str) -> dict[str, Any]:
        logger.info("doctor_chat_tool_call", tool="get_patient_case", args={"patient_id": patient_id})
        return await _exec_get_patient_case(patient_id)

    async def get_synthesis(patient_id: str) -> dict[str, Any]:
        logger.info("doctor_chat_tool_call", tool="get_synthesis", args={"patient_id": patient_id})
        return await _exec_get_synthesis(patient_id)

    async def search_clinical_data(query: str, patient_id: str | None = None) -> dict[str, Any]:
        logger.info(
            "doctor_chat_tool_call",
            tool="search_clinical_data",
            args={"query": query, "patient_id": patient_id},
        )
        return await _exec_search_clinical_data(query, patient_id)

    return [
        FunctionTool(
            name="list_patients",
            description=(
                "List all patients currently in the system. Returns each patient's ID, "
                "name, analysis status, number of findings, and whether a synthesis report exists."
            ),
            func=list_patients,
        ),
        FunctionTool(
            name="search_patient",
            description="Search for a patient by name or partial patient ID.",
            func=search_patient,
            input_model=SearchPatientInput,
        ),
        FunctionTool(
            name="load_patient",
            description="Load a patient's clinical context and navigate the UI to that patient.",
            func=load_patient,
            input_model=LoadPatientInput,
        ),
        FunctionTool(
            name="get_patient_case",
            description=(
                "Get the overall case for a patient, including episodes, latest findings, "
                "synthesis reports, and retrieved patient-scoped search context."
            ),
            func=get_patient_case,
            input_model=GetPatientCaseInput,
        ),
        FunctionTool(
            name="get_findings",
            description="Get clinical findings for a patient, optionally filtered by modality.",
            func=get_findings,
            input_model=GetFindingsInput,
        ),
        FunctionTool(
            name="get_synthesis",
            description="Get the diagnostic synthesis report for a patient.",
            func=get_synthesis,
            input_model=GetSynthesisInput,
        ),
        FunctionTool(
            name="search_clinical_data",
            description="Search indexed clinical documents across one or all patients.",
            func=search_clinical_data,
            input_model=SearchClinicalDataInput,
        ),
    ]


async def _maybe_handle_direct_patient_navigation(
    messages: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Bypass model routing for explicit patient navigation requests."""
    if not messages:
        return None

    latest_user_message = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    ).strip()
    if not latest_user_message:
        return None

    patient_match = _PATIENT_ID_QUERY_RE.search(latest_user_message)
    if not patient_match:
        return None

    normalized = latest_user_message.lower()
    if not any(verb in normalized for verb in _LOAD_PATIENT_VERBS):
        return None

    patient_id = patient_match.group(1).upper()
    result = await _exec_load_patient(patient_id)
    if result.get("action") == "navigate":
        logger.info("doctor_chat_direct_navigation", patient_id=patient_id)
        return {
            "reply": f"I've navigated to patient {patient_id}.",
            "action": {
                "type": "navigate",
                "patient_id": patient_id,
            },
        }

    return {
        "reply": result.get("error", f"Patient {patient_id} not found."),
        "action": None,
    }


async def _maybe_handle_direct_patient_case_query(
    messages: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Bypass model routing for explicit patient case summary questions."""
    if not messages:
        return None

    latest_user_message = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    ).strip()
    if not latest_user_message:
        return None

    patient_match = _PATIENT_ID_QUERY_RE.search(latest_user_message)
    if not patient_match:
        return None

    normalized = latest_user_message.lower()
    if not any(term in normalized for term in _CASE_QUERY_TERMS):
        return None

    patient_id = patient_match.group(1).upper()
    case = await _exec_get_patient_case(patient_id)
    if case.get("error"):
        return {"reply": case["error"], "action": None}

    lines = [
        f"Case summary for {case['patient_id']} ({case['name']}).",
        f"Status: {case['status']}. Episodes: {case['episodes']}. Active episode: {case['active_episode'] or 'none'}.",
        f"Findings: {case['findings_count']}.",
    ]

    latest_findings = case.get("latest_findings", [])
    if latest_findings:
        lines.append("Recent findings:")
        for finding in latest_findings[:3]:
            lines.append(f"- {finding['modality']}: {finding['summary']}")

    synthesis = case.get("synthesis", [])
    if synthesis:
        lines.append(f"Latest synthesis: {synthesis[-1].get('summary', '')}")
    elif case.get("search_hits"):
        lines.append(f"Retrieved context: {case['search_hits'][0].get('summary', '')}")

    logger.info("doctor_chat_direct_case_query", patient_id=patient_id)
    return {"reply": "\n".join(lines), "action": None}


# ── Main Chat Handler ────────────────────────────────────────


async def handle_doctor_chat(
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Process a doctor chat turn with GPT-4o function calling.

    Parameters
    ----------
    messages:
        The conversation history (list of {role, content} dicts from
        the client). The system prompt is prepended automatically.

    Returns
    -------
    dict with keys:
        - reply (str): The assistant's text response.
        - action (dict | None): A UI action like {"type": "navigate", "patient_id": "P001"}.
    """
    latest_user_message = next(
        (msg.get("content", "") for msg in reversed(messages) if msg.get("role") == "user"),
        "",
    ).strip()

    with start_span(
        "doctor_chat.handle_turn",
        tracer_name="doctor_chat",
        attributes={
            "mednexus.message_count": len(messages),
            "mednexus.latest_user_message": latest_user_message[:200],
        },
    ) as span:
        try:
            direct_case_result = await _maybe_handle_direct_patient_case_query(messages)
            if direct_case_result is not None:
                if span is not None:
                    span.set_attribute("mednexus.chat.route", "direct_case_query")
                return direct_case_result

            direct_result = await _maybe_handle_direct_patient_navigation(messages)
            if direct_result is not None:
                if span is not None:
                    span.set_attribute("mednexus.chat.route", "direct_navigation")
                return direct_result

            ui_action_ref: dict[str, Any] = {}
            agent = Agent(
                client=create_agent_framework_chat_client(),
                name="MedNexus Clinical Concierge",
                instructions=_SYSTEM_PROMPT,
                tools=_build_framework_tools(ui_action_ref),
            )
            session = agent.create_session()
            agent_messages = [
                Message(role=msg["role"], text=msg["content"])
                for msg in messages
                if msg.get("role") in {"user", "assistant"}
            ]

            logger.info(
                "doctor_chat_openai_request",
                deployment=settings.azure_openai_deployment,
                managed_identity=settings.use_managed_identity,
                runtime="microsoft_agent_framework",
            )
            if span is not None:
                span.set_attribute("mednexus.chat.route", "agent_framework")
                span.set_attribute("mednexus.ai.deployment", settings.azure_openai_deployment)

            response = await agent.run(agent_messages, session=session)
            if span is not None and ui_action_ref:
                span.set_attribute("mednexus.ui_action_type", ui_action_ref.get("type"))
                span.set_attribute("mednexus.ui_action_patient_id", ui_action_ref.get("patient_id"))
            return {
                "reply": response.text or "",
                "action": ui_action_ref or None,
            }
        except Exception as exc:
            mark_span_failure(span, exc)
            logger.exception("doctor_chat_openai_failed")
            return {
                "reply": "The assistant is temporarily unavailable. Please try again in a moment.",
                "action": None,
            }
