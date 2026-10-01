"""LangChain document loaders for diary and schedule files.

CSV, XLSX, DOCX, and ICS become text. Images are OCR'd by
UnstructuredImageLoader. No Google OAuth.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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

_LOADER_NAMES = {
    "csv": "CSVLoader",
    "xlsx": "UnstructuredExcelLoader",
    "docx": "UnstructuredWordDocumentLoader",
    "ics": "TextLoader",
    "image": "UnstructuredImageLoader",
}


def kind_for(filename: str) -> str:
    """Map a filename to a loader kind, or raise UnsupportedFileError."""
    suffix = Path(filename or "").suffix.lower()
    kind = ALLOWED.get(suffix)
    if kind is None:
        raise UnsupportedFileError(suffix or "missing extension")
    return kind


def _loader_cls(kind: str):
    import langchain_community.document_loaders as loaders

    return getattr(loaders, _LOADER_NAMES[kind])


def _load_path(kind: str, path: str) -> str:
    docs = _loader_cls(kind)(path).load()
    return "\n".join(getattr(doc, "page_content", "") or "" for doc in docs).strip()


def load_upload(filename: str, data: bytes) -> tuple[str, bytes]:
    """Return (text, image_bytes). image_bytes is empty unless the upload is a photo.

    Empty bytes, an unsupported type, or a loader that yields no text (and is
    not an image) raise before any LLM call.
    """
    if not data:
        raise EmptyFileError("empty file")
    kind = kind_for(filename)
    suffix = Path(filename).suffix.lower() or ".bin"
    image = data if kind == "image" else b""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(data)
        handle.flush()
        try:
            text = _load_path(kind, handle.name)
        except UnsupportedFileError:
            raise
        except Exception as exc:
            raise EmptyFileError(f"unreadable file: {exc}") from exc
    if not text and kind != "image":
        raise EmptyFileError("loader returned no text")
    return text, image
