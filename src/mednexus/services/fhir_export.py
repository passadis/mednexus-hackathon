"""FHIR R4 export – converts a signed-off Episode into a standards-compliant Bundle.

Produces a FHIR R4 *transaction* Bundle containing:
  - Patient          (demographics)
  - DiagnosticReport (synthesis report + recommendations)
  - Observation(s)   (one per ClinicalFinding)

Only episodes with ``approved_by`` set are eligible for export.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fhir.resources.bundle import Bundle, BundleEntry, BundleEntryRequest
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.diagnosticreport import DiagnosticReport
from fhir.resources.humanname import HumanName
from fhir.resources.identifier import Identifier
from fhir.resources.meta import Meta
from fhir.resources.narrative import Narrative
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient
from fhir.resources.reference import Reference

from mednexus.models.clinical_context import ClinicalContext, ClinicalFinding, Episode


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_patient(ctx: ClinicalContext) -> Patient:
    """Build a minimal FHIR Patient from PatientDemographics."""
    names = []
    if ctx.patient.name:
        parts = ctx.patient.name.split()
        names.append(
            HumanName(
                family=parts[-1] if len(parts) > 1 else parts[0],
                given=parts[:-1] if len(parts) > 1 else [],
            )
        )

    identifiers = [
        Identifier(system="urn:mednexus:patient-id", value=ctx.patient.patient_id),
    ]
    if ctx.patient.mrn:
        identifiers.append(Identifier(system="urn:mednexus:mrn", value=ctx.patient.mrn))

    return Patient(
        id=ctx.patient.patient_id,
        meta=Meta(profile=["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]),
        identifier=identifiers,
        name=names or None,
        gender=ctx.patient.gender or None,
        birthDate=ctx.patient.date_of_birth or None,
    )


def _make_observation(finding: ClinicalFinding, patient_ref: str) -> Observation:
    """Map a ClinicalFinding to FHIR Observation."""
    modality_map = {
        "radiology_image": ("http://loinc.org", "18748-4", "Diagnostic Imaging Report"),
        "clinical_text": ("http://loinc.org", "51855-5", "Patient Note"),
        "audio_transcript": ("http://loinc.org", "34764-0", "General medicine Consultation note"),
        "lab_result": ("http://loinc.org", "26436-6", "Laboratory Studies"),
    }
    system, code, display = modality_map.get(
        finding.modality, ("http://loinc.org", "75321-0", "Clinical Finding")
    )

    return Observation(
        id=finding.finding_id,
        status="final",
        code=CodeableConcept(
            coding=[Coding(system=system, code=code, display=display)],
            text=f"{finding.modality} finding by {finding.source_agent}",
        ),
        subject=Reference(reference=patient_ref),
        effectiveDateTime=finding.timestamp.isoformat()
        if hasattr(finding.timestamp, "isoformat")
        else str(finding.timestamp),
        valueString=finding.summary,
        note=[{"text": f"Confidence: {finding.confidence:.0%}"}] if finding.confidence else None,
    )


def _make_diagnostic_report(
    ep: Episode,
    patient_ref: str,
    observation_refs: list[str],
) -> DiagnosticReport:
    """Build DiagnosticReport from the episode's SynthesisReport."""
    synth = ep.synthesis

    conclusion = synth.summary if synth else ""
    if synth and synth.recommendations:
        conclusion += "\n\nRecommendations:\n" + "\n".join(
            f"- {r}" for r in synth.recommendations
        )

    coded_dx: list[CodeableConcept] = []
    if synth and synth.discrepancies:
        for disc in synth.discrepancies:
            coded_dx.append(
                CodeableConcept(text=f"[{disc.severity.upper()}] {disc.description}")
            )

    text_div = conclusion.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return DiagnosticReport(
        id=synth.report_id if synth else uuid.uuid4().hex[:12],
        status="final" if ep.approved_by else "preliminary",
        code=CodeableConcept(
            coding=[
                Coding(
                    system="http://loinc.org",
                    code="60591-5",
                    display="Patient Summary Document",
                )
            ],
            text=f"MedNexus Diagnostic Synthesis – {ep.label}",
        ),
        subject=Reference(reference=patient_ref),
        effectiveDateTime=ep.updated_at.isoformat()
        if hasattr(ep.updated_at, "isoformat")
        else str(ep.updated_at),
        issued=_now_iso(),
        performer=[Reference(display=ep.approved_by)] if ep.approved_by else None,
        result=[Reference(reference=r) for r in observation_refs],
        conclusion=conclusion,
        conclusionCode=coded_dx or None,
        text=Narrative(
            status="generated",
            div=f'<div xmlns="http://www.w3.org/1999/xhtml"><pre>{text_div}</pre></div>',
        ),
    )


def episode_to_fhir_bundle(ctx: ClinicalContext, episode: Episode) -> dict:
    """Convert a signed-off Episode into a FHIR R4 transaction Bundle.

    Returns the Bundle as a plain dict ready for JSON serialisation.
    Raises ``ValueError`` if the episode has not been approved.
    """
    if not episode.approved_by:
        raise ValueError("Only signed-off episodes can be exported to FHIR.")

    patient = _make_patient(ctx)
    patient_ref = f"Patient/{patient.id}"

    observations: list[Observation] = []
    obs_refs: list[str] = []
    for finding in episode.findings:
        obs = _make_observation(finding, patient_ref)
        observations.append(obs)
        obs_refs.append(f"Observation/{obs.id}")

    report = _make_diagnostic_report(episode, patient_ref, obs_refs)

    entries: list[BundleEntry] = []
    for resource in [patient, report, *observations]:
        rtype = resource.__resource_type__
        rid = resource.id
        entries.append(
            BundleEntry(
                fullUrl=f"urn:uuid:{rid}",
                resource=resource,
                request=BundleEntryRequest(method="PUT", url=f"{rtype}/{rid}"),
            )
        )

    bundle = Bundle(
        id=uuid.uuid4().hex[:12],
        type="transaction",
        timestamp=_now_iso(),
        meta=Meta(
            profile=["http://hl7.org/fhir/R4/bundle.html"],
            tag=[Coding(system="urn:mednexus", code="fhir-export", display="MedNexus FHIR Export")],
        ),
        entry=entries,
    )

    return bundle.model_dump(mode="json", exclude_none=True)
