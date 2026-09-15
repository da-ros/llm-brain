"""distill() orchestrator — Factory Method over LangChain loaders + LLM extraction."""

from __future__ import annotations

from pathlib import Path

from base import documents_to_content, first_page, first_section, load, source_name
from config import get_settings
from exceptions import CorruptFileError, ETLError, FileTooLargeError, LoaderError
from jsonl import write_triples
from llm_client import LLMServiceClient, TripleExtractor
from logging_setup import log_with_correlation
from triples import Triple, triple_from_llm


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
) -> list[Triple]:
    """Load a document, ask the LLM Service to emit triples, optionally write JSONL.

    1. Select LangChain loader by MIME type
    2. Load content (text / OCR / multimodal)
    3. POST content to LLM Service (base Qwen3.5-4B)
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

    try:
        documents = load(str(path), mime_type=mime_type)
        content = documents_to_content(documents)
    except ETLError:
        raise
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise LoaderError(f"LangChain loader failed: {exc}") from exc
    source_file = source_name(str(path), documents)
    page = first_page(documents)
    section = first_section(documents)

    client = llm_client or LLMServiceClient()
    raw_triples = client.extract_triples(
        content,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    triples: list[Triple] = []
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
