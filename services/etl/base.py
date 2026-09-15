"""LangChain loader selection layer.

Maps MIME type → langchain_community.document_loaders adapter.
Exposes `select(file_path)` and `load(file_path)` as specified in the change.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from exceptions import UnsupportedFileTypeError
from loaders import (
    documents_to_content,
    first_page,
    first_section,
    is_supported_mime,
    resolve_loader_class,
    source_name,
    supported_types_message,
)
from logging_setup import logger


def detect_mime(*, file_path: str | None = None, content: bytes | None = None) -> str:
    """Detect MIME type from bytes (python-magic), not from the file extension.

    Falls back to mimetypes only when libmagic is unavailable (local/dev).
    """
    payload = content
    if payload is None and file_path:
        payload = Path(file_path).read_bytes()
    if payload is None:
        raise UnsupportedFileTypeError("No file content available for MIME detection")

    try:
        import magic

        mime = magic.from_buffer(payload, mime=True)
        if mime:
            return mime.split(";")[0].strip().lower()
    except Exception as exc:
        logger.debug("python-magic unavailable or failed: %s", exc)

    if file_path:
        guessed, _ = mimetypes.guess_type(file_path)
        if guessed:
            return guessed.split(";")[0].strip().lower()

    raise UnsupportedFileTypeError("Cannot detect MIME type")


def select(file_path: str, mime_type: str | None = None) -> type:
    """Factory Method: return the LangChain loader adapter class for this file."""
    mime = mime_type or detect_mime(file_path=file_path)
    loader_cls = resolve_loader_class(mime)
    if loader_cls is None:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {mime}. {supported_types_message()}"
        )
    logger.info("Selecting LangChain loader for mime=%s path=%s", mime, file_path)
    return loader_cls


def load(file_path: str, mime_type: str | None = None) -> list[Any]:
    """Select the loader and return LangChain Documents."""
    loader_cls = select(file_path, mime_type=mime_type)
    return loader_cls(file_path).load()


__all__ = [
    "detect_mime",
    "documents_to_content",
    "first_page",
    "first_section",
    "is_supported_mime",
    "load",
    "select",
    "source_name",
    "supported_types_message",
]
