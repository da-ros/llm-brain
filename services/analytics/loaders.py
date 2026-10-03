"""Upload classification for analytics ingest.

Which file types analytics accepts, and which carry image bytes to the LLM.
Text extraction is the ETL service's job (POST /parse) — analytics never
parses documents itself, the same way it never opens Chroma (see rag_client).
"""

from __future__ import annotations

from pathlib import Path

import etl_client
from exceptions import EmptyFileError, UnsupportedFileError

ALLOWED = {
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".docx": "docx",
    ".ics": "ics",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
}


def kind_for(filename: str) -> str:
    """Map a filename to an ingest kind, or raise UnsupportedFileError."""
    suffix = Path(filename or "").suffix.lower()
    kind = ALLOWED.get(suffix)
    if kind is None:
        raise UnsupportedFileError(suffix or "missing extension")
    return kind


async def load_upload(filename: str, data: bytes, *, correlation_id: str) -> tuple[str, bytes]:
    """Return (text, image_bytes) for one upload.

    Image uploads skip the ETL parse (OCR is out of scope in this iteration)
    and keep their bytes for the LLM. Everything else gets its text from the
    ETL service. Empty bytes, an unsupported type, or an ETL failure raise
    before any LLM call.
    """
    if not data:
        raise EmptyFileError("empty file")
    kind = kind_for(filename)
    if kind == "image":
        return "", data
    text = await etl_client.parse_text(filename=filename, data=data, correlation_id=correlation_id)
    if not text:
        raise EmptyFileError("ETL parse returned no text")
    return text, b""
