"""Triple dataclass — subject-predicate-object with metadata.

Extraction itself is LLM-first (see llm_client). This module only models the
record and enriches metadata (source_file, page, section, timestamp, confidence).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Triple:
    """Subject-predicate-object knowledge unit extracted by the LLM."""

    subject: str
    predicate: str
    object: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the triple to a JSON-compatible dict."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "metadata": self.metadata,
        }

    def to_json_line(self) -> str:
        """Serialize as a single JSON Lines row."""
        return json.dumps(self.to_dict(), ensure_ascii=False)


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.7
    return max(0.0, min(1.0, confidence))


def enrich_metadata(
    raw_metadata: dict[str, Any] | None,
    *,
    source_file: str,
    user_id: str,
    page: int | None = None,
    section: str | None = None,
    timestamp: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Fill required metadata fields without dropping LLM-provided extras."""
    metadata = dict(raw_metadata or {})
    metadata["source_file"] = source_file
    metadata["user_id"] = user_id
    metadata["timestamp"] = timestamp or datetime.now(UTC).isoformat()
    if page is not None:
        metadata.setdefault("page", page)
    if section:
        metadata.setdefault("section", section)
    metadata["confidence"] = _clamp_confidence(
        confidence if confidence is not None else metadata.get("confidence", 0.7)
    )
    return metadata


def triple_from_llm(
    payload: dict[str, Any],
    *,
    source_file: str,
    user_id: str,
    page: int | None = None,
    section: str | None = None,
) -> Triple | None:
    """Build a Triple from one LLM JSON object, or None if required keys are missing."""
    subject = payload.get("subject")
    predicate = payload.get("predicate")
    obj = payload.get("object")
    if not subject or not predicate or not obj:
        return None
    raw_meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return Triple(
        subject=str(subject).strip(),
        predicate=str(predicate).strip(),
        object=str(obj).strip(),
        metadata=enrich_metadata(
            raw_meta,
            source_file=source_file,
            user_id=user_id,
            page=page,
            section=section,
        ),
    )
