"""LangChain document loaders wired by MIME type.

Every parser is an out-of-the-box `langchain_community.document_loaders` class
(or a thin adapter that still exposes `.load()`). No hand-rolled PDF/HTML/EML/OCR
parsers and no bespoke Tesseract pipeline.

LangChain is imported inside `.load()` so `select()` stays cheap and testable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from exceptions import CorruptFileError, LoaderError
from logging_setup import logger

IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/gif",
    "image/webp",
    "image/bmp",
}

VIDEO_MIMES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/mpeg",
    "video/x-matroska",
}

HTML_MIMES = {"text/html", "application/xhtml+xml"}
EMAIL_MIMES = {"message/rfc822", "application/vnd.ms-outlook"}
DOCX_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
EXCEL_MIMES = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
CSV_MIMES = {"text/csv", "text/tab-separated-values"}
# Text formats handled by TextLoader (chat attachments: diaries, calendars).
TEXT_EXTRA_MIMES = {"text/markdown", "text/calendar"}

SUPPORTED_MIMES = (
    {"application/pdf", "text/plain"}
    | HTML_MIMES
    | EMAIL_MIMES
    | DOCX_MIMES
    | EXCEL_MIMES
    | CSV_MIMES
    | TEXT_EXTRA_MIMES
    | IMAGE_MIMES
    | VIDEO_MIMES
)


def _has_text(documents: list[Any]) -> bool:
    return any(getattr(doc, "page_content", "").strip() for doc in documents)


def _run_loader(loader_cls: Any, file_path: str, label: str, **kwargs: Any) -> list[Any]:
    try:
        return loader_cls(file_path, **kwargs).load()
    except Exception as exc:
        raise LoaderError(f"{label} failed: {exc}") from exc


def _pdf_loader_classes() -> tuple[Any, Any, Any]:
    from langchain_community.document_loaders import (
        PDFPlumberLoader,
        PyPDFLoader,
        UnstructuredPDFLoader,
    )

    return PyPDFLoader, PDFPlumberLoader, UnstructuredPDFLoader


def _text_loader_class() -> Any:
    from langchain_community.document_loaders import TextLoader

    return TextLoader


def _html_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredHTMLLoader

    return UnstructuredHTMLLoader


def _email_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredEmailLoader

    return UnstructuredEmailLoader


def _word_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredWordDocumentLoader

    return UnstructuredWordDocumentLoader


def _csv_loader_class() -> Any:
    from langchain_community.document_loaders import CSVLoader

    return CSVLoader


def _excel_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredExcelLoader

    return UnstructuredExcelLoader


def _image_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredImageLoader

    return UnstructuredImageLoader


def _video_loader_class() -> Any:
    from langchain_community.document_loaders import UnstructuredFileLoader

    return UnstructuredFileLoader


class PdfLoaderAdapter:
    """PDF strategy: PyPDFLoader → PDFPlumberLoader → UnstructuredPDFLoader (OCR)."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        pypdf_cls, plumber_cls, unstructured_cls = _pdf_loader_classes()

        for loader_cls, label in (
            (pypdf_cls, "PyPDFLoader"),
            (plumber_cls, "PDFPlumberLoader"),
        ):
            try:
                documents = loader_cls(self.file_path).load()
            except Exception as exc:
                logger.debug("%s failed for %s: %s", label, self.file_path, exc)
                continue
            if _has_text(documents):
                logger.info("LangChain loader selected: %s", label)
                return documents

        try:
            documents = unstructured_cls(self.file_path).load()
        except Exception as exc:
            raise LoaderError(f"PDF loader failed: {exc}") from exc
        logger.info("LangChain loader selected: UnstructuredPDFLoader (OCR via Unstructured)")
        return documents


class TextLoaderAdapter:
    """Plain-text strategy wrapping LangChain TextLoader."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(
            _text_loader_class(), self.file_path, "TextLoader", autodetect_encoding=True
        )
        logger.info("LangChain loader selected: TextLoader")
        return documents


class UnstructuredHTMLLoaderAdapter:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(_html_loader_class(), self.file_path, "UnstructuredHTMLLoader")
        logger.info("LangChain loader selected: UnstructuredHTMLLoader")
        return documents


class UnstructuredEmailLoaderAdapter:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(_email_loader_class(), self.file_path, "UnstructuredEmailLoader")
        logger.info("LangChain loader selected: UnstructuredEmailLoader")
        return documents


class UnstructuredWordLoaderAdapter:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(
            _word_loader_class(), self.file_path, "UnstructuredWordDocumentLoader"
        )
        logger.info("LangChain loader selected: UnstructuredWordDocumentLoader")
        return documents


class CsvLoaderAdapter:
    """CSV strategy wrapping LangChain CSVLoader."""

    def __init__(self, file_path: str, delimiter: str = ",") -> None:
        self.file_path = file_path
        self.delimiter = delimiter

    def load(self) -> list[Any]:
        documents = _run_loader(
            _csv_loader_class(),
            self.file_path,
            "CSVLoader",
            csv_args={"delimiter": self.delimiter},
        )
        logger.info("LangChain loader selected: CSVLoader (delimiter=%r)", self.delimiter)
        return documents


class TsvLoaderAdapter(CsvLoaderAdapter):
    """TSV strategy — the same CSVLoader with a tab delimiter."""

    def __init__(self, file_path: str) -> None:
        super().__init__(file_path, delimiter="\t")


class ExcelLoaderAdapter:
    """XLS/XLSX strategy wrapping UnstructuredExcelLoader."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(_excel_loader_class(), self.file_path, "UnstructuredExcelLoader")
        logger.info("LangChain loader selected: UnstructuredExcelLoader")
        return documents


class UnstructuredImageLoaderAdapter:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        # ocr_only reads words with Tesseract. The default image strategy is
        # hi_res, which downloads a layout model before that OCR runs.
        documents = _run_loader(
            _image_loader_class(),
            self.file_path,
            "UnstructuredImageLoader",
            strategy="ocr_only",
            languages=["eng", "spa"],
        )
        logger.info("LangChain loader selected: UnstructuredImageLoader (ocr_only)")
        return documents


class VideoFileLoader:
    """Local video strategy wrapping UnstructuredFileLoader (LangChain out-of-the-box)."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        documents = _run_loader(_video_loader_class(), self.file_path, "UnstructuredFileLoader")
        logger.info("LangChain loader selected: UnstructuredFileLoader (video)")
        return documents


def resolve_loader_class(mime_type: str) -> type | None:
    """Map MIME type → loader adapter class (Factory Method lookup)."""
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime == "application/pdf":
        return PdfLoaderAdapter
    if mime == "text/plain":
        return TextLoaderAdapter
    if mime in HTML_MIMES:
        return UnstructuredHTMLLoaderAdapter
    if mime in EMAIL_MIMES:
        return UnstructuredEmailLoaderAdapter
    if mime in DOCX_MIMES:
        return UnstructuredWordLoaderAdapter
    if mime in EXCEL_MIMES:
        return ExcelLoaderAdapter
    if mime == "text/tab-separated-values":
        return TsvLoaderAdapter
    if mime == "text/csv":
        return CsvLoaderAdapter
    if mime in TEXT_EXTRA_MIMES:
        return TextLoaderAdapter
    if mime in IMAGE_MIMES:
        return UnstructuredImageLoaderAdapter
    if mime in VIDEO_MIMES or mime.startswith("video/"):
        return VideoFileLoader
    return None


def is_supported_mime(mime_type: str) -> bool:
    """Return True if a LangChain loader is registered for this MIME type."""
    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime in VIDEO_MIMES or mime.startswith("video/"):
        return True
    return mime in SUPPORTED_MIMES


def supported_types_message() -> str:
    return (
        "Supported types: text/plain, text/markdown, text/calendar (ICS), text/csv, TSV, "
        "application/pdf, text/html, message/rfc822, DOCX, Excel (xls/xlsx), "
        "image (png/jpeg/tiff/gif/webp/bmp), video (mp4/webm/quicktime)"
    )


def documents_to_content(documents: list[Any]) -> str:
    """Join LangChain Documents into one content blob with page markers."""
    parts: list[str] = []
    for document in documents:
        text = (getattr(document, "page_content", None) or "").strip()
        if not text:
            continue
        metadata = getattr(document, "metadata", None) or {}
        page = metadata.get("page")
        header = f"\n--- page {page} ---\n" if page is not None else "\n"
        parts.append(header + text)
    content = "".join(parts).strip()
    if not content:
        raise CorruptFileError("Loader returned no extractable content")
    return content


def first_page(documents: list[Any]) -> int | None:
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        page = metadata.get("page")
        if page is not None:
            try:
                return int(page)
            except (TypeError, ValueError):
                continue
    return None


def first_section(documents: list[Any]) -> str | None:
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        section = metadata.get("section") or metadata.get("category")
        if section:
            return str(section)
    return None


def source_name(file_path: str, documents: list[Any]) -> str:
    for document in documents:
        metadata = getattr(document, "metadata", None) or {}
        source = metadata.get("source") or metadata.get("filename")
        if source:
            return Path(str(source)).name
    return Path(file_path).name
