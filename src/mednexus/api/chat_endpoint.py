"""Doctor Chat – conversational concierge backed by GPT-4o function calling.

The chat endpoint lets an attending physician ask natural-language questions
such as "How many patients do we have?", "Is there an Emily Johnson?", or
"Bring up Emily" and automatically surfaces Cosmos data or triggers patient
navigation in the UI.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from openai import AsyncAzureOpenAI

from mednexus.config import settings
from mednexus.services.cosmos_client import get_cosmos_manager

logger = structlog.get_logger()

# ── Tool Definitions (OpenAI function-calling schema) ────────

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_patients",
            "description": (
                "List all patients currently in the system. Returns each "
                "patient's ID, name, analysis status, number of findings, "
                "and whether a synthesis report exists."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_patient",
            "description": (
                "Search for a patient by name (case-insensitive, partial match). "
                "Returns matching patient IDs and names."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Patient name or partial name to search for.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_patient",
            "description": (
                "Load a patient's full clinical context (demographics, status, "
                "findings, synthesis) and signal the UI to navigate to that "
                "patient's dashboard view."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The patient ID (e.g. P001).",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_findings",
            "description": (
                "Get the clinical findings for a specific patient, optionally "
                "filtered by modality (radiology_image, clinical_text, "
                "audio_transcript)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The patient ID.",
                    },
                    "modality": {
                        "type": "string",
                        "description": "Optional modality filter.",
                        "enum": [
                            "radiology_image",
                            "clinical_text",
                            "audio_transcript",
                        ],
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_synthesis",
            "description": (
                "Get the diagnostic synthesis report for a patient, including "
                "the summary, cross-modality notes, discrepancies, and "
                "recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The patient ID.",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clinical_data",
            "description": (
                "Perform a hybrid (keyword + vector) semantic search across "
                "all indexed clinical documents — findings, X-ray analyses, "
                "transcripts, and notes.  Use this when the doctor asks broad "
                "clinical questions like 'which patients have lung opacity?' "
                "or 'any cardiac abnormalities across all patients?'.  Can "
                "optionally be scoped to a single patient."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The clinical search query (e.g. 'lung opacity', 'cardiac findings').",
                    },
                    "patient_id": {
                        "type": "string",
                        "description": "Optional patient ID to scope the search to.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

_SYSTEM_PROMPT = """\
You are the MedNexus Clinical Concierge, an AI assistant embedded in a \
multi-agent healthcare platform.  You help the attending physician navigate \
patient data, review findings, and understand synthesis reports.

You have access to the following tools:
- list_patients: enumerate all patients in the system
- search_patient: fuzzy-search patients by name
- load_patient: navigate the UI to a specific patient
- get_findings: retrieve clinical findings for a patient
- get_synthesis: retrieve the diagnostic synthesis report
- search_clinical_data: semantic hybrid search across ALL clinical documents (findings, X-ray reports, transcripts)

Guidelines:
• Be concise and clinical in tone.
• When the user asks to "bring up" or "show" a patient, call load_patient.
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


_TOOL_DISPATCH = {
    "list_patients": lambda _args: _exec_list_patients(),
    "search_patient": lambda args: _exec_search_patient(args["query"]),
    "load_patient": lambda args: _exec_load_patient(args["patient_id"]),
    "get_findings": lambda args: _exec_get_findings(args["patient_id"], args.get("modality")),
    "get_synthesis": lambda args: _exec_get_synthesis(args["patient_id"]),
    "search_clinical_data": lambda args: _exec_search_clinical_data(args["query"], args.get("patient_id")),
}


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
    client = AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )

    # Build message list with system prompt
    full_messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *messages,
    ]

    ui_action: dict[str, Any] | None = None

    try:
        # Allow up to 5 tool-call rounds
        for _ in range(5):
            resp = await client.chat.completions.create(
                model=settings.azure_openai_deployment,
                messages=full_messages,
                tools=_TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1024,
            )

            choice = resp.choices[0]

            # If no tool calls, we have the final answer
            if not choice.message.tool_calls:
                return {
                    "reply": choice.message.content or "",
                    "action": ui_action,
                }

            # Append assistant message with tool calls
            full_messages.append(choice.message.model_dump())

            # Execute each tool call
            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}

                logger.info("doctor_chat_tool_call", tool=fn_name, args=fn_args)

                handler = _TOOL_DISPATCH.get(fn_name)
                if handler is None:
                    result = {"error": f"Unknown tool: {fn_name}"}
                else:
                    result = await handler(fn_args)

                # Capture navigate actions for the UI
                if fn_name == "load_patient" and result.get("action") == "navigate":
                    ui_action = {
                        "type": "navigate",
                        "patient_id": result["patient_id"],
                    }

                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

        # Ran out of rounds
        return {
            "reply": "I apologize, I wasn't able to complete that request. Could you try again?",
            "action": ui_action,
        }

    finally:
        await client.close()
