import os

from microsoft.opentelemetry import use_microsoft_opentelemetry

LOGGER_NAME = "matchproof"


def configure_telemetry() -> bool:
    """Send traces to Application Insights when APPLICATIONINSIGHTS_CONNECTION_STRING is set."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return False
    use_microsoft_opentelemetry(enable_azure_monitor=True, logger_name=LOGGER_NAME)
    return True
