import logging
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
except ImportError:
    OTLPSpanExporter = None

from .config import get_config

logger = logging.getLogger(__name__)

_tracer = None


def initialize_telemetry() -> None:
    global _tracer
    if _tracer is not None:
        return

    config = get_config()
    resource = Resource(attributes={
        "service.name": "multi-agent-system",
        "service.version": "1.0.0"
    })
    provider = TracerProvider(resource=resource)

    if config.otel_exporter_endpoint and OTLPSpanExporter is not None:
        try:
            exporter = OTLPSpanExporter(endpoint=config.otel_exporter_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"OpenTelemetry exporter initialized: {config.otel_exporter_endpoint}")
        except Exception as e:
            logger.warning(f"OpenTelemetry exporter failed: {e}")
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif config.otel_exporter_endpoint and OTLPSpanExporter is None:
        logger.warning("OTLPSpanExporter unavailable; falling back to console exporter")
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OpenTelemetry console exporter configured")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)


def get_tracer():
    global _tracer
    if _tracer is None:
        initialize_telemetry()
    return _tracer
