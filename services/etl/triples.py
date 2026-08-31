"""Triple Data Model and Extraction.

Defines the Triple dataclass and rule-based extraction patterns.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Triple:
    """Subject-Predicate-Object triple with metadata.

    This is the fundamental unit of knowledge extracted from documents.
    """

    subject: str
    predicate: str
    object: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert triple to dictionary."""
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "metadata": self.metadata,
        }

    def to_json_line(self) -> str:
        """Convert triple to JSON Line format."""
        import json

        return json.dumps(self.to_dict())


# --- Rule-based extraction patterns ---

# Pattern: "X is Y"
PATTERN_IS = re.compile(
    r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+is\s+([a-z]+(?:\s+[a-z]+)*)",
    re.IGNORECASE,
)

# Pattern: "X has Y"
PATTERN_HAS = re.compile(
    r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+has\s+([a-z]+(?:\s+[a-z]+)*)",
    re.IGNORECASE,
)

# Pattern: "X performs Y"
PATTERN_PERFORMS = re.compile(
    r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+performs?\s+([a-z]+(?:\s+[a-z]+)*)",
    re.IGNORECASE,
)

# Pattern: "X takes Y" (medications)
PATTERN_TAKES = re.compile(
    r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+takes?\s+([a-z]+(?:\s+[a-z]+)*)",
    re.IGNORECASE,
)

# Pattern: "X was diagnosed with Y"
PATTERN_DIAGNOSED = re.compile(
    r"([A-Z][a-z]+(?:\s+[a-z]+)*)\s+was\s+diagnosed\s+with\s+([a-z]+(?:\s+[a-z]+)*)",
    re.IGNORECASE,
)

# All patterns with their predicates
PATTERNS = [
    (PATTERN_IS, "is"),
    (PATTERN_HAS, "has"),
    (PATTERN_PERFORMS, "performs"),
    (PATTERN_TAKES, "takes"),
    (PATTERN_DIAGNOSED, "diagnosed_with"),
]


def extract_triples(
    text: str,
    source_file: str = "",
    page: int | None = None,
    section: str | None = None,
) -> list[Triple]:
    """Extract triples from text using rule-based patterns.

    Args:
        text: Raw text to extract triples from
        source_file: Source file name for metadata
        page: Page number (if applicable)
        section: Section name (if applicable)

    Returns:
        List of extracted triples
    """
    triples = []
    metadata = {
        "source_file": source_file,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.8,  # Rule-based confidence
    }
    if page is not None:
        metadata["page"] = page
    if section is not None:
        metadata["section"] = section

    # Split text into sentences
    sentences = re.split(r"[.!?]+", text)

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 5:
            continue

        # Try each pattern
        for pattern, predicate in PATTERNS:
            matches = pattern.findall(sentence)
            for subject, obj in matches:
                subject = subject.strip()
                obj = obj.strip()

                # Skip very short or very long extractions
                if len(subject) < 2 or len(obj) < 2:
                    continue
                if len(subject) > 100 or len(obj) > 100:
                    continue

                triple = Triple(
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    metadata={**metadata},
                )
                triples.append(triple)

    return triples
