"""distill() orchestrator — Factory Method over LangChain loaders + LLM extraction."""

from __future__ import annotations

from pathlib import Path

from base import documents_to_content, first_page, first_section, load, source_name
from calendar_events import event_triples
from config import get_settings
from exceptions import (
    CorruptFileError,
    ETLError,
    FileTooLargeError,
    LLMExtractionError,
    LoaderError,
)
from jsonl import write_triples
from llm_client import LLMServiceClient, TripleExtractor
from logging_setup import log_with_correlation
from triples import Triple, enrich_metadata, triple_from_llm

_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".heic",
    ".heif",
}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".mpeg", ".mpg"}


def _visual_kind(mime_type: str | None, file_path: str) -> str | None:
    """image or video when the file is a photo or clip. None for documents."""
    mime = (mime_type or "").split(";")[0].strip().lower()
    suffix = Path(file_path).suffix.lower()
    if mime.startswith("image/") or suffix in _IMAGE_SUFFIXES:
        return "image"
    if mime.startswith("video/") or suffix in _VIDEO_SUFFIXES:
        return "video"
    return None


def _read_content(file_path: str, mime_type: str | None) -> tuple[list, str]:
    """Return loader documents and their text. A photo or clip with no words yields empty text."""
    try:
        documents = load(file_path, mime_type=mime_type)
        return documents, documents_to_content(documents)
    except CorruptFileError:
        if _visual_kind(mime_type, file_path):
            return [], ""
        raise


def _description(
    client: TripleExtractor,
    payload: bytes,
    *,
    kind: str,
    filename: str,
    user_id: str,
    correlation_id: str,
) -> str:
    """Ask the model what the photo or clip shows when no words were extracted."""
    describe = getattr(client, "describe_media", None)
    if describe is None:
        describe = LLMServiceClient().describe_media
    text = describe(
        payload,
        kind=kind,
        filename=filename,
        user_id=user_id,
        correlation_id=correlation_id,
    )
    if not isinstance(text, str) or not text.strip():
        raise LLMExtractionError("The model returned an empty description")
    return text.strip()


def _is_calendar(file_path: str, mime_type: str | None, filename: str | None) -> bool:
    mime = (mime_type or "").split(";")[0].strip().lower()
    suffixes = {Path(file_path).suffix.lower(), Path(filename or "").suffix.lower()}
    return mime in {"text/calendar", "text/x-vcalendar"} or ".ics" in suffixes


def _one_note(
    text: str,
    *,
    source_file: str,
    user_id: str,
    page: int | None,
    section: str | None,
) -> list[Triple]:
    """A photo or clip is one memory. Its fields stay in that one passage."""
    body = " ".join(text.split())
    if not body:
        raise CorruptFileError("No text could be read from the file")
    return [
        Triple(
            subject=source_file,
            predicate="records",
            object=body,
            metadata=enrich_metadata(
                {"source notes": "Kept as one note"},
                source_file=source_file,
                user_id=user_id,
                page=page,
                section=section,
            ),
        )
    ]


def _from_calendar(path: Path, *, source_file: str, user_id: str) -> list[Triple]:
    """Read each VEVENT as one fact. The model is not asked to split the calendar."""
    triples: list[Triple] = []
    for item in event_triples(path.read_text(encoding="utf-8", errors="replace")):
        triple = triple_from_llm(item, source_file=source_file, user_id=user_id)
        if triple is not None:
            triples.append(triple)
    if not triples:
        raise CorruptFileError("Calendar has no events")
    return triples


def distill(
    file_path: str,
    *,
    user_id: str,
    document_id: str,
    mime_type: str | None = None,
    llm_client: TripleExtractor | None = None,
    output_dir: str | None = None,
    correlation_id: str = "no-id",
    write_output: bool = True,
    filename: str | None = None,
) -> list[Triple]:
    """Load a document, ask the LLM Service to emit triples, optionally write JSONL.

    1. Select LangChain loader by MIME type
    2. Load content (text / OCR). A photo or clip with no words is described from its bytes.
    3. A photo or clip is saved as one note. Other text goes to the LLM Service for triples.
    4. Enrich metadata and write data/triples/{user_id}/{document_id}.jsonl
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    settings = get_settings()
    size = path.stat().st_size
    if size > settings.MAX_FILE_SIZE:
        raise FileTooLargeError(f"File too large: {size} bytes (max {settings.MAX_FILE_SIZE})")

    log_with_correlation(
        correlation_id,
        "info",
        f"Starting ETL pipeline: {path.name} ({size} bytes) user_id={user_id}",
    )

    if _is_calendar(str(path), mime_type, filename):
        given_name = Path(filename).name if filename else ""
        source_file = given_name or path.name
        triples = _from_calendar(path, source_file=source_file, user_id=user_id)
        if write_output:
            target_dir = output_dir or settings.TRIPLES_OUTPUT_DIR
            output_path = write_triples(
                triples,
                user_id=user_id,
                document_id=document_id,
                output_dir=target_dir,
            )
            log_with_correlation(
                correlation_id,
                "info",
                f"Saved {len(triples)} calendar events to {output_path}",
            )
        return triples

    try:
        documents, content = _read_content(str(path), mime_type)
    except ETLError:
        raise
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise LoaderError(f"LangChain loader failed: {exc}") from exc
    client = llm_client or LLMServiceClient()
    visual = _visual_kind(mime_type, str(path))
    if not content.strip() and visual:
        log_with_correlation(
            correlation_id,
            "info",
            f"No text extracted; asking the model to describe the {visual}",
        )
        content = _description(
            client,
            path.read_bytes(),
            kind=visual,
            filename=path.name,
            user_id=user_id,
            correlation_id=correlation_id,
        )
    given_name = Path(filename).name if filename else ""
    source_file = given_name or source_name(str(path), documents)
    page = first_page(documents)
    section = first_section(documents)

    if visual:
        triples = _one_note(
            content,
            source_file=source_file,
            user_id=user_id,
            page=page,
            section=section,
        )
    else:
        raw_triples = client.extract_triples(
            content,
            user_id=user_id,
            correlation_id=correlation_id,
        )

        triples = []
        for item in raw_triples:
            if not isinstance(item, dict):
                continue
            triple = triple_from_llm(
                item,
                source_file=source_file,
                user_id=user_id,
                page=page,
                section=section,
            )
            if triple is not None:
                triples.append(triple)

        if not triples:
            raise CorruptFileError("LLM returned no valid subject-predicate-object triples")

    if write_output:
        target_dir = output_dir or settings.TRIPLES_OUTPUT_DIR
        output_path = write_triples(
            triples,
            user_id=user_id,
            document_id=document_id,
            output_dir=target_dir,
        )
        log_with_correlation(
            correlation_id,
            "info",
            f"Saved {len(triples)} triples to {output_path}",
        )

    return triples
