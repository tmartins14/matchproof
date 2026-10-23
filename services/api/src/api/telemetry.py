import os

from microsoft.opentelemetry import use_microsoft_opentelemetry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

LOGGER_NAME = "matchproof"
CONSOLE_ENV = (
    "MATCHPROOF_TRACE_CONSOLE"  # "1": print spans to the console (local development)
)


def configure_telemetry() -> bool:
    """Send traces to Application Insights when APPLICATIONINSIGHTS_CONNECTION_STRING is set.

    Otherwise a plain tracer provider is installed so spans still carry real trace ids (a claim's
    `checker.trace_id`), with a console exporter when MATCHPROOF_TRACE_CONSOLE=1.
    """
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        use_microsoft_opentelemetry(enable_azure_monitor=True, logger_name=LOGGER_NAME)
        return True
    provider = TracerProvider()
    if os.environ.get(CONSOLE_ENV) == "1":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return False
