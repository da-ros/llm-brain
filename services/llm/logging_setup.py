"""Structured logging with correlation ID on every line.

Format: %(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="no-id")

LOG_FORMAT = "%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"


class CorrelationFilter(logging.Filter):
    """Add correlation_id to all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        existing = getattr(record, "correlation_id", None)
        if not existing:
            record.correlation_id = correlation_id_var.get()
        return True


def configure_logging() -> logging.Logger:
    """Configure process-wide logging and return the llm-service logger."""
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
    correlation_filter = CorrelationFilter()
    root = logging.getLogger()
    if not any(isinstance(item, CorrelationFilter) for item in root.filters):
        root.addFilter(correlation_filter)
    logger = logging.getLogger("llm-service")
    if not any(isinstance(item, CorrelationFilter) for item in logger.filters):
        logger.addFilter(correlation_filter)
    return logger


logger = configure_logging()


def log_with_correlation(correlation_id: str, level: str, message: str) -> None:
    """Log a message with an explicit correlation_id."""
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)
