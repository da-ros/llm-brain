"""Analytics Service errors."""

from __future__ import annotations


class AnalyticsError(Exception):
    """Base error for the Analytics Service."""


class UnsupportedFileError(AnalyticsError):
    """File type is not csv, xlsx, docx, ics, or an image."""


class EmptyFileError(AnalyticsError):
    """File is empty or parsing produced no text."""


class ETLUpstreamError(AnalyticsError):
    """ETL Service could not parse the file — unreachable or non-200 (HTTP 503)."""


class LLMTimeoutError(AnalyticsError):
    """LLM Service timed out (HTTP 504)."""


class LLMUpstreamError(AnalyticsError):
    """LLM Service returned 5xx, was unreachable, or emitted invalid JSON (HTTP 502)."""


class InvalidInferenceJSONError(AnalyticsError):
    """LLM text was not the required inference JSON. Retried once, then 502."""
