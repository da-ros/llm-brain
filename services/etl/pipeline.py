"""ETL Pipeline — Distillation Orchestrator.

Routes files to correct parser and collects triples.
"""

import json
from pathlib import Path

from services.etl.base import DocumentParser
from services.etl.parsers.pdf import PdfParser
from services.etl.parsers.html import HtmlParser
from services.etl.parsers.eml import EmlParser
from services.etl.parsers.ocr import OcrParser
from services.etl.triples import Triple


# Initialize parsers
PARSERS: list[DocumentParser] = [
    PdfParser(),
    HtmlParser(),
    EmlParser(),
    OcrParser(),
]


def get_parser(file_path: str) -> DocumentParser | None:
    """Get the appropriate parser for a file.

    Args:
        file_path: Path to the file

    Returns:
        Parser instance or None if no parser supports this file
    """
    for parser in PARSERS:
        if parser.supports(file_path):
            return parser
    return None


def distill(file_path: str) -> list[Triple]:
    """Distill a document into triples.

    This is the main orchestrator function that:
    1. Selects the appropriate parser
    2. Parses the document
    3. Returns extracted triples

    Args:
        file_path: Path to the document

    Returns:
        List of extracted triples

    Raises:
        ValueError: If file not found or no parser supports this file type
    """
    path = Path(file_path)

    # Validate file exists
    if not path.exists():
        raise ValueError(f"File not found: {file_path}")

    # Get appropriate parser
    parser = get_parser(file_path)
    if parser is None:
        raise ValueError(f"No parser available for file type: {path.suffix}")

    # Parse document
    triples = parser.parse(file_path)

    return triples


def save_triples(
    triples: list[Triple],
    output_path: str,
) -> int:
    """Save triples to JSONL file.

    Args:
        triples: List of triples to save
        output_path: Path to output JSONL file

    Returns:
        Number of triples saved
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        for triple in triples:
            f.write(triple.to_json_line() + "\n")

    return len(triples)
