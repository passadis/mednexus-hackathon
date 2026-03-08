"""Azure Functions – Blob trigger for automatic file intake.

When a file is uploaded to the ``mednexus-intake`` container, this
function fires and kicks off the agent pipeline via the Orchestrator.
"""

from __future__ import annotations

import json
import logging

import azure.functions as func

logger = logging.getLogger("mednexus.functions")

app = func.FunctionApp()


@app.blob_trigger(
    arg_name="blob",
    path="mednexus-intake/{name}",
    connection="AZURE_STORAGE_CONNECTION_STRING",
)
async def on_file_upload(blob: func.InputStream) -> None:
    """Triggered when a new file lands in the intake blob container.

    Steps:
      1. Extract metadata (filename, size).
      2. Classify the file via the Clinical Sorter.
      3. Get or create the Clinical Context in Cosmos DB.
      4. Hand off to the Orchestrator for routing.
    """
    filename = blob.name or "unknown"
    blob_uri = f"az://mednexus-intake/{filename}"
    logger.info("Blob trigger fired: %s (%d bytes)", filename, blob.length or 0)

    try:
        # Import here to avoid cold-start penalty for other functions
        from mednexus.agents.clinical_sorter import ClinicalSorterAgent
        from mednexus.agents.orchestrator import OrchestratorAgent
        from mednexus.services.cosmos_client import get_cosmos_manager
        from mednexus.a2a import get_a2a_bus

        sorter = ClinicalSorterAgent()
        orchestrator = OrchestratorAgent()
        bus = get_a2a_bus()
        bus.register(sorter)
        bus.register(orchestrator)

        # Classify
        med_file = await sorter.classify_file(filename.split("/")[-1], blob_uri)
        logger.info("Classified %s as %s (patient: %s)", filename, med_file.file_type, med_file.patient_id)

        if not med_file.patient_id:
            logger.warning("Could not extract patient_id from %s", filename)
            return

        # Get or create context
        cosmos = get_cosmos_manager()
        ctx = await cosmos.get_context(med_file.patient_id)
        if ctx is None:
            ctx = await cosmos.create_context(med_file.patient_id)

        # Dispatch to orchestrator
        task_id = await orchestrator.ingest_file(med_file, ctx)
        await cosmos.upsert_context(ctx)

        logger.info("Dispatched task %s for patient %s", task_id, med_file.patient_id)

    except Exception:
        logger.exception("Error processing blob %s", filename)
        raise
