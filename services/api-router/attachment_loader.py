"""Read a chat attachment with the LangChain loaders ETL and Analytics use.

The extracted text is for the current question only. Nothing here writes
documents, GridFS, or RAG.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mimeutil import detect_mime

FILE_KINDS = (
    ("Documents", "PDF, Word, text, Markdown"),
    ("Spreadsheets", "Excel, CSV"),
    ("Pages and mail", "HTML, email"),
    ("Images", "PNG, JPEG, GIF, WebP, TIFF, BMP"),
    ("Video", "MP4, MOV, WebM, AVI, MKV"),
)

_EXT_KIND = {
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "text",
    ".markdown": "text",
    ".text": "text",
    ".ics": "text",
    ".csv": "csv",
    ".tsv": "tsv",
    ".html": "html",
    ".htm": "html",
    ".eml": "email",
    ".msg": "email",
    ".doc": "word",
    ".docx": "word",
    ".xls": "excel",
    ".xlsx": "excel",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".avi": "video",
    ".mkv": "video",
    ".mpeg": "video",
    ".mpg": "video",
}

_MIME_KIND = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
    "text/csv": "csv",
    "text/tab-separated-values": "tsv",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "message/rfc822": "email",
    "application/vnd.ms-outlook": "email",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "application/vnd.ms-excel": "excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
}


class UnsupportedAttachmentError(ValueError):
    pass


class EmptyAttachmentError(ValueError):
    pass


def supported_summary() -> str:
    return "; ".join(f"{name}: {items}" for name, items in FILE_KINDS)


def load_attachment(filename: str, data: bytes) -> str:
    if not data:
        raise EmptyAttachmentError(filename)
    kind = _kind(filename, data)
    suffix = Path(filename or "").suffix.lower() or _suffix_for(kind)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"attachment{suffix}"
        path.write_bytes(data)
        docs = _load(kind, path)
    parts = [doc.page_content.strip() for doc in docs if getattr(doc, "page_content", "").strip()]
    return "\n\n".join(parts)


def _kind(filename: str, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _EXT_KIND:
        return _EXT_KIND[suffix]
    mime = detect_mime(data, filename)
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("text/"):
        return "text"
    kind = _MIME_KIND.get(mime)
    if kind is None:
        raise UnsupportedAttachmentError(suffix or mime or "unknown")
    return kind


def _suffix_for(kind: str) -> str:
    return {
        "pdf": ".pdf",
        "csv": ".csv",
        "tsv": ".tsv",
        "html": ".html",
        "email": ".eml",
        "word": ".docx",
        "excel": ".xlsx",
        "image": ".png",
        "video": ".mp4",
    }.get(kind, ".txt")


def _load(kind: str, path: Path):
    if kind == "pdf":
        return _load_pdf(path)
    if kind == "text":
        return _text_loader()(str(path), autodetect_encoding=True).load()
    if kind == "csv":
        return _csv_loader()(str(path)).load()
    if kind == "tsv":
        return _csv_loader()(str(path), csv_args={"delimiter": "\t"}).load()
    if kind == "html":
        return _html_loader()(str(path)).load()
    if kind == "email":
        return _email_loader()(str(path)).load()
    if kind == "word":
        return _word_loader()(str(path)).load()
    if kind == "excel":
        return _excel_loader()(str(path)).load()
    if kind == "image":
        return _image_loader()(str(path)).load()
    if kind == "video":
        return _video_loader()(str(path)).load()
    raise UnsupportedAttachmentError(kind)


def _load_pdf(path: Path):
    from langchain_community.document_loaders import (
        PDFPlumberLoader,
        PyPDFLoader,
        UnstructuredPDFLoader,
    )

    for loader_cls in (PyPDFLoader, PDFPlumberLoader, UnstructuredPDFLoader):
        try:
            docs = loader_cls(str(path)).load()
        except Exception:
            continue
        if any(getattr(doc, "page_content", "").strip() for doc in docs):
            return docs
    return UnstructuredPDFLoader(str(path)).load()


def _text_loader():
    from langchain_community.document_loaders import TextLoader

    return TextLoader


def _csv_loader():
    from langchain_community.document_loaders import CSVLoader

    return CSVLoader


def _html_loader():
    from langchain_community.document_loaders import UnstructuredHTMLLoader

    return UnstructuredHTMLLoader


def _email_loader():
    from langchain_community.document_loaders import UnstructuredEmailLoader

    return UnstructuredEmailLoader


def _word_loader():
    from langchain_community.document_loaders import UnstructuredWordDocumentLoader

    return UnstructuredWordDocumentLoader


def _excel_loader():
    from langchain_community.document_loaders import UnstructuredExcelLoader

    return UnstructuredExcelLoader


def _image_loader():
    from langchain_community.document_loaders import UnstructuredImageLoader

    return UnstructuredImageLoader


def _video_loader():
    from langchain_community.document_loaders import UnstructuredFileLoader

    return UnstructuredFileLoader
