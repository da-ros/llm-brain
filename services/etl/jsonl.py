"""JSONL writer with per-user isolation.

Output path: data/triples/{user_id}/{document_id}.jsonl
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from triples import Triple


def triples_path(output_dir: str, user_id: str, document_id: str) -> Path:
    """Return the per-user JSONL path for a document."""
    return Path(output_dir) / user_id / f"{document_id}.jsonl"


def write_triples(
    triples: list[Triple],
    *,
    user_id: str,
    document_id: str,
    output_dir: str,
) -> Path:
    """Write one JSON object per line. Creates the user directory if needed."""
    path = triples_path(output_dir, user_id, document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for triple in triples:
            handle.write(triple.to_json_line() + "\n")
    return path
