"""Labeled scam corpus. Cached vectors are filled via RAG POST /embed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from config import get_settings


@dataclass(frozen=True)
class CorpusItem:
    id: str
    label: str
    source: str
    text: str
    vector: tuple[float, ...] | None = None


def load_corpus(path: str | None = None) -> list[CorpusItem]:
    """Read corpus.jsonl. Missing file yields an empty gallery."""
    corpus_path = Path(path or get_settings().CORPUS_PATH)
    if not corpus_path.is_file():
        return []
    items: list[CorpusItem] = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        items.append(
            CorpusItem(
                id=str(row["id"]),
                label=str(row["label"]),
                source=str(row["source"]),
                text=str(row["text"]),
            )
        )
    return items


def cosine(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_l = sum(a * a for a in left) ** 0.5 or 1.0
    norm_r = sum(b * b for b in right) ** 0.5 or 1.0
    return dot / (norm_l * norm_r)


def nearest(
    queries: list[list[float]],
    gallery: list[CorpusItem],
) -> tuple[CorpusItem, float] | None:
    """Best cosine of any query vector against the cached text gallery."""
    best: tuple[CorpusItem, float] | None = None
    for query in queries:
        for item in gallery:
            if not item.vector:
                continue
            score = cosine(query, item.vector)
            if best is None or score > best[1]:
                best = (item, score)
    return best
