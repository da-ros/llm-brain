"""OCR an image with the LangChain image loader. Video is never passed here."""

from __future__ import annotations

import os
import tempfile
from typing import Any


def _image_loader(path: str) -> Any:
    from langchain_community.document_loaders import UnstructuredImageLoader

    return UnstructuredImageLoader(path)


def ocr_image(payload: bytes, suffix: str = ".png") -> str:
    """Return OCR text. Empty string means the image had no readable text."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
    documents = _image_loader(handle.name).load()
    os.unlink(handle.name)
    parts = [str(getattr(doc, "page_content", "") or "").strip() for doc in documents]
    return "\n".join(part for part in parts if part).strip()
