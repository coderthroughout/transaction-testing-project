from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource

_tracer: trace.Tracer = None


def setup_telemetry() -> trace.Tracer:
    global _tracer
    if _tracer is not None:
        return _tracer

    # If another SDK (e.g. Omium) already configured a real TracerProvider, reuse it
    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider):
        _tracer = existing.get_tracer("transaction.agent", "1.0.0")
        return _tracer

    # No provider yet — set up our own with console output
    resource = Resource.create({"service.name": "stablecoin-txn-agent"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("transaction.agent", "1.0.0")
    return _tracer


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        return setup_telemetry()
    return _tracer
