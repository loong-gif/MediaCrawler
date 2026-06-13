# -*- coding: utf-8 -*-
"""
OpenTelemetry observability module for MediaCrawler.
Configures traces, logs, and metrics with Superlog as the OTLP endpoint.
"""

from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

# ── Superlog configuration ───────────────────────────────────────────────────
SUPERLOG_ENDPOINT = "https://intake.superlog.sh"
SUPERLOG_PUBLIC_TOKEN = "sl_public_QqoHtWP3QEuqp86o2QOGFVRax0zKUgt1VLdYyQIPiII"


def superlog_headers() -> dict:
    """Return the authorization headers required by the Superlog intake endpoint."""
    return {"Authorization": f"Bearer {SUPERLOG_PUBLIC_TOKEN}"}


# ── Shared resource ──────────────────────────────────────────────────────────
_resource = Resource.create(
    {
        "service.name": "mediacrawler",
        "deployment.environment.name": "local",
        "vcs.repository.url.full": "https://github.com/superloglabs/skills",
    }
)

# ── Module-scope instruments (initialised by init_observability) ─────────────
tracer: Optional[trace.Tracer] = None
meter: Optional[metrics.Meter] = None

_observability_initialised = False


def init_observability(app=None) -> None:
    """
    Bootstrap the full OpenTelemetry stack (traces, logs, metrics).

    Call once at startup.  If *app* is a FastAPI instance the ASGI
    instrumentor is attached automatically.
    """
    global tracer, meter, _observability_initialised

    if _observability_initialised:
        return
    _observability_initialised = True

    headers = superlog_headers()

    # ── Traces ───────────────────────────────────────────────────────────────
    span_exporter = OTLPSpanExporter(
        endpoint=f"{SUPERLOG_ENDPOINT}/v1/traces",
        headers=headers,
    )
    tracer_provider = TracerProvider(resource=_resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    tracer = trace.get_tracer("mediacrawler")

    # ── Metrics ──────────────────────────────────────────────────────────────
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{SUPERLOG_ENDPOINT}/v1/metrics",
        headers=headers,
    )
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(
        resource=_resource, metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(meter_provider)
    meter = metrics.get_meter("mediacrawler")

    # ── Logs ─────────────────────────────────────────────────────────────────
    log_exporter = OTLPLogExporter(
        endpoint=f"{SUPERLOG_ENDPOINT}/v1/logs",
        headers=headers,
    )
    logger_provider = LoggerProvider(resource=_resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # Attach OTel handler to root logger so all existing loggers emit OTel logs
    import logging
    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

    logging.getLogger().addHandler(otel_handler)

    # LoggingInstrumentor injects trace_id / span_id into log records
    LoggingInstrumentor().instrument(set_logging_format=True)

    # ── HTTPX auto-instrumentation ───────────────────────────────────────────
    HTTPXClientInstrumentor().instrument()

    # ── FastAPI (optional) ───────────────────────────────────────────────────
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass
