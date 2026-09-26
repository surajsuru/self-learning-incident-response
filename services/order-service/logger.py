import logging
import sys
from pythonjsonlogger import jsonlogger
from opentelemetry import trace


class TraceCorrelationFilter(logging.Filter):
    """Automatically attaches current OpenTelemetry trace_id and span_id to every log record."""
    def filter(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = None
            record.span_id = None
        return True

class EndpointFilter(logging.Filter):
    """Silences noisy periodic polling from Prometheus (/metrics) and health checks (/health)."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "/metrics" not in msg and "/health" not in msg

# Silence uvicorn scrape spam across all services
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())


def get_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(span_id)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    handler.setFormatter(formatter)
    handler.addFilter(TraceCorrelationFilter())

    if not logger.handlers:
        logger.addHandler(handler)

    return logger
