"""OpenTelemetry / Application Insights bootstrap and span helpers."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Any

import structlog

from mednexus.config import settings

logger = structlog.get_logger()

_lock = threading.Lock()
_configured = False


def configure_observability() -> None:
    """Configure Azure Monitor and Agent Framework instrumentation once."""
    global _configured

    if _configured or not settings.applicationinsights_connection_string:
        return

    with _lock:
        if _configured:
            return

        from azure.monitor.opentelemetry import configure_azure_monitor

        auth_string_present = bool(os.getenv("APPLICATIONINSIGHTS_AUTHENTICATION_STRING"))
        logger.info(
            "azure_monitor_configuration_detected",
            managed_identity=settings.use_managed_identity,
            connection_string_present=bool(settings.applicationinsights_connection_string),
            auth_string_present=auth_string_present,
            client_id_present=bool(settings.managed_identity_client_id),
        )
        if settings.use_managed_identity and not auth_string_present:
            logger.warning("azure_monitor_auth_string_missing")

        kwargs: dict[str, Any] = {
            "connection_string": settings.applicationinsights_connection_string,
            "logger_name": "mednexus",
        }
        credential = _get_azure_monitor_credential()
        if credential is not None:
            kwargs["credential"] = credential

        configure_azure_monitor(**kwargs)
        _enable_agent_framework_instrumentation()
        _configured = True
        logger.info("observability_configured")


def _get_azure_monitor_credential():
    """Return a token credential for Entra-authenticated telemetry export."""
    if not settings.use_managed_identity:
        return None

    try:
        from azure.identity import ManagedIdentityCredential

        credential = ManagedIdentityCredential(
            client_id=settings.managed_identity_client_id or None
        )
        logger.info(
            "azure_monitor_managed_identity_enabled",
            client_id=bool(settings.managed_identity_client_id),
        )
        return credential
    except Exception as exc:
        logger.warning("azure_monitor_credential_unavailable", error=str(exc))
        return None


def _enable_agent_framework_instrumentation() -> None:
    """Enable Agent Framework OpenTelemetry hooks when available."""
    try:
        from agent_framework.observability import enable_instrumentation
    except Exception as exc:
        logger.warning("agent_framework_observability_unavailable", error=str(exc))
        return

    try:
        enable_instrumentation()
        logger.info("agent_framework_observability_enabled")
    except Exception as exc:
        logger.warning("agent_framework_observability_failed", error=str(exc))


def _normalize_span_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return str(value)


def _get_tracer(name: str):
    try:
        from opentelemetry import trace

        return trace.get_tracer(f"mednexus.{name}")
    except Exception:
        return None


@contextmanager
def start_span(name: str, *, tracer_name: str = "app", attributes: dict[str, Any] | None = None):
    """Create a span when OpenTelemetry is available, otherwise yield ``None``."""
    tracer = _get_tracer(tracer_name)
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                normalized = _normalize_span_value(value)
                if normalized is not None:
                    span.set_attribute(key, normalized)
        yield span


def mark_span_failure(span: Any, exc: Exception) -> None:
    """Record an exception on a span when OpenTelemetry is available."""
    if span is None:
        return

    try:
        from opentelemetry.trace import Status, StatusCode

        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:
        return
