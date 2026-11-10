"""LangChain document loaders wired by MIME type.

Documents, mail, and spreadsheets use an out-of-the-box
`langchain_community.document_loaders` class. Photos and scanned PDFs are
read with Tesseract in `ocr.py` so Unstructured's partition modules, which
load the unstructured_inference package at import time, are never loaded.

LangChain is imported inside `.load()` so `select()` stays cheap and testable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from exceptions import CorruptFileError, LoaderError
from logging_setup import logger
from ocr import ocr_image, ocr_pdf

IMAGE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
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
}
EXCEL_MIMES = {
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
CSV_MIMES = {"text/csv", "text/tab-separated-values"}
# Text formats handled by TextLoader (chat attachments: diaries, calendars).
TEXT_EXTRA_MIMES = {"text/markdown", "text/calendar", "text/x-vcalendar"}

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


def _pdf_text_loaders() -> tuple[Any, Any]:
    from langchain_community.document_loaders import PDFPlumberLoader, PyPDFLoader

    return PyPDFLoader, PDFPlumberLoader


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


class PdfLoaderAdapter:
    """PDF strategy: PyPDFLoader, then PDFPlumberLoader, then Tesseract on each page."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        pypdf_cls, plumber_cls = _pdf_text_loaders()

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

        pages = ocr_pdf(self.file_path)
        if not pages:
            raise LoaderError("PDF loader failed: Tesseract found no text")
        logger.info("Tesseract OCR selected for scanned PDF")
        return [_page(text, self.file_path, page) for page, text in pages]


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


class ImageLoaderAdapter:
    """Read words in a photo with Tesseract. An empty result is still a document."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        text = ocr_image(self.file_path)
        logger.info("Tesseract OCR selected for image")
        return [_page(text, self.file_path)]


class VideoFileLoader:
    """A clip has no extracted words, same as a photo Tesseract cannot read."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def load(self) -> list[Any]:
        logger.info("Video has no extracted text; the model will describe it")
        return [_page("", self.file_path)]


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
        return ImageLoaderAdapter
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
        "image (png/jpeg/tiff/gif/webp/bmp/heic), video (mp4/webm/quicktime)"
    )


class _Page:
    def __init__(self, page_content: str, metadata: dict[str, Any]) -> None:
        self.page_content = page_content
        self.metadata = metadata


def _page(text: str, source: str, page: int | None = None) -> _Page:
    metadata: dict[str, Any] = {"source": source}
    if page is not None:
        metadata["page"] = page
    return _Page(text, metadata)


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
