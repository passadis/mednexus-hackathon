"""Shared test fixtures."""

from __future__ import annotations

import pytest

from mednexus.models.clinical_context import ClinicalContext, ContextStatus


@pytest.fixture
def sample_context() -> ClinicalContext:
    """Return a minimal ClinicalContext for testing."""
    return ClinicalContext(patient_id="P1234", status=ContextStatus.INTAKE)


@pytest.fixture
def finalized_context() -> ClinicalContext:
    """Return a fully-populated ClinicalContext."""
    ctx = ClinicalContext(patient_id="P5678", status=ContextStatus.FINALIZED)
    ctx.demographics.name = "Jane Doe"
    return ctx
