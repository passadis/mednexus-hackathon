"""Multi-Agent Orchestration Workflow – Microsoft Agent Framework.

Defines the MedNexus clinical data processing pipeline using AF
``ConcurrentBuilder``, ``SequentialBuilder``, ``Agent``, and
``@tool``-decorated functions.

Pipeline shape::

    ClinicalSorter
         │
    ┌────┴────┐
    │         │
  Vision   Historian       (ConcurrentBuilder)
    │         │
    └────┬────┘
         │
   DiagnosticSynthesis     (aggregator)

The workflow is built once at startup and executed per-patient file.
Specialist agents wrap existing domain logic as AF tools.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from agent_framework import Agent, tool
from agent_framework.orchestrations import ConcurrentBuilder
from agent_framework._workflows._agent_executor import AgentExecutorResponse

from mednexus.services.af_client import get_af_client

logger = structlog.get_logger()


# ── Specialist tools (wrap existing domain logic) ────────────


@tool
async def classify_medical_file(
    filename: Annotated[str, "The filename to classify (e.g. P001_chest_xray.png)."],
) -> str:
    """Classify a medical file by its extension and extract a patient ID from the filename convention (PATIENTID_description.ext)."""
    import json
    from mednexus.models.medical_files import MedicalFile

    file_type = MedicalFile.classify(filename)
    import re
    m = re.match(r"^(P\d{4,})", filename, re.IGNORECASE)
    patient_id = m.group(1).upper() if m else ""
    return json.dumps({
        "filename": filename,
        "file_type": file_type.value,
        "patient_id": patient_id,
    })


@tool
async def analyze_medical_image(
    file_uri: Annotated[str, "URI of the medical image to analyse."],
    patient_id: Annotated[str, "The patient ID owning this image."],
) -> str:
    """Read a medical image via the MCP gateway and produce structured radiology findings using GPT-4o multimodal vision."""
    import base64
    import json
    import re

    from mednexus.services.llm_client import get_llm_client

    filename = file_uri.split("/")[-1].split("\\")[-1]
    m = re.match(r"^(P\d{4,})", filename, re.IGNORECASE)

    if m:
        from mednexus.mcp.clinical_gateway import get_clinical_gateway
        gw = get_clinical_gateway()
        result = await gw.fetch_medical_image(
            image_id=filename, patient_id=m.group(1).upper(), agent_id="af-vision",
        )
        image_bytes = base64.b64decode(result["content_base64"])
    else:
        from mednexus.mcp import create_mcp_server
        mcp = create_mcp_server()
        image_bytes = await mcp.read_bytes(file_uri)

    image_b64 = base64.b64encode(image_bytes).decode()
    client = get_llm_client()
    raw = await client.chat_with_image(
        system_prompt=(
            "You are a board-certified radiologist AI. Respond ONLY in valid JSON "
            "with keys: region, observations, impression, confidence, recommendations."
        ),
        user_prompt="Analyse this medical image.",
        image_b64=image_b64,
        response_format={"type": "json_object"},
    )
    return raw


@tool
async def retrieve_patient_history(
    patient_id: Annotated[str, "The patient ID to search history for."],
    query: Annotated[str, "Clinical query to search for in the patient's records."],
) -> str:
    """Search Azure AI Search for historical clinical documents matching a patient, returning relevant records for RAG synthesis."""
    import json
    from mednexus.services.search_client import search_patient_documents

    results = await search_patient_documents(patient_id, query, top=10)
    hits = []
    for doc in results:
        hits.append({
            "content_type": doc.get("content_type", ""),
            "summary": (doc.get("analysis_summary") or doc.get("content", ""))[:500],
            "score": round(doc.get("@search.score", 0), 3),
        })
    return json.dumps({"patient_id": patient_id, "results": hits})


@tool
async def synthesize_findings(
    patient_id: Annotated[str, "The patient ID."],
    findings_json: Annotated[str, "JSON string containing all findings to synthesise."],
) -> str:
    """Perform cross-modality diagnostic synthesis across radiology images, clinical text, and transcripts. Produces a unified report with discrepancies and recommendations."""
    import json
    from mednexus.services.llm_client import get_llm_client

    client = get_llm_client()
    raw = await client.chat(
        system_prompt=(
            "You are a senior clinical decision-support AI. Perform a Cross-Modality "
            "Check across all findings. Respond in JSON with keys: summary, "
            "cross_modality_notes, discrepancies, recommendations, confidence."
        ),
        user_prompt=f"Patient: {patient_id}\n\nFindings:\n{findings_json}",
        temperature=0.1,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return raw


# ── AF Agent definitions ─────────────────────────────────────


def build_sorter_agent() -> Agent:
    """Clinical Sorter – classifies incoming medical files."""
    return Agent(
        client=get_af_client(),
        name="ClinicalSorter",
        description="Classifies incoming medical files by type and extracts patient IDs.",
        instructions=(
            "You are the intake desk of MedNexus. When given a filename, "
            "use the classify_medical_file tool to determine its type and "
            "extract the patient ID."
        ),
        tools=[classify_medical_file],
    )


def build_vision_agent() -> Agent:
    """Vision Specialist – analyses medical images via GPT-4o multimodal."""
    return Agent(
        client=get_af_client(),
        name="VisionSpecialist",
        description="Analyses medical images and produces structured radiology findings.",
        instructions=(
            "You are a board-certified radiologist AI assistant. When given a "
            "medical image URI, use the analyze_medical_image tool to produce "
            "structured findings including region, observations, impression, "
            "and confidence score."
        ),
        tools=[analyze_medical_image],
    )


def build_historian_agent() -> Agent:
    """Patient Historian – performs RAG over clinical records."""
    return Agent(
        client=get_af_client(),
        name="PatientHistorian",
        description="Retrieves and synthesises patient history using RAG via Azure AI Search.",
        instructions=(
            "You are a clinical informaticist. Use the retrieve_patient_history "
            "tool to search the hospital's knowledge base for relevant records, "
            "then summarise the patient's clinical history."
        ),
        tools=[retrieve_patient_history],
    )


def build_synthesis_agent() -> Agent:
    """Diagnostic Synthesis – cross-modality analysis."""
    return Agent(
        client=get_af_client(),
        name="DiagnosticSynthesis",
        description="Synthesises multi-modal findings into a unified diagnostic report.",
        instructions=(
            "You are a senior clinical decision-support AI. Use the "
            "synthesize_findings tool to perform cross-modality analysis "
            "across all available findings for a patient."
        ),
        tools=[synthesize_findings],
    )


# ── Workflow definition ──────────────────────────────────────


def build_clinical_workflow() -> dict[str, Any]:
    """Build the AF Workflow expressing the MedNexus pipeline.

    Pipeline:
      [Vision ∥ Historian] (concurrent) → Synthesis (aggregator)

    The Sorter agent runs separately as a gateway before this workflow.
    ``ConcurrentBuilder`` provides the fan-out/fan-in orchestration:
    Vision and Historian run in parallel, then Synthesis aggregates.

    Returns a dict with the built ``Workflow`` and standalone ``Sorter`` agent.
    """
    sorter = build_sorter_agent()
    vision = build_vision_agent()
    historian = build_historian_agent()
    synthesis = build_synthesis_agent()

    # Fan-out: Vision and Historian run concurrently
    # Fan-in: callable aggregator collects results, then Synthesis agent merges
    async def aggregate_and_synthesize(
        responses: list[AgentExecutorResponse],
    ) -> str:
        """Collect concurrent findings and run DiagnosticSynthesis."""
        import json as _json

        combined = []
        for resp in responses:
            combined.append(resp.value.text if hasattr(resp.value, "text") else str(resp.value))
        findings_blob = _json.dumps(combined)
        result = await synthesis.run(f"Synthesise these findings:\n{findings_blob}")
        return result.text or ""

    analysis_workflow = (
        ConcurrentBuilder(participants=[vision, historian])
        .with_aggregator(aggregate_and_synthesize)
        .build()
    )

    logger.info(
        "af_workflow_built",
        agents=["ClinicalSorter", "VisionSpecialist", "PatientHistorian", "DiagnosticSynthesis"],
        pattern="sorter → concurrent(vision ∥ historian) → synthesis",
    )
    return {
        "sorter": sorter,
        "analysis": analysis_workflow,
    }
