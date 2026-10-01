"""Ingest orchestration: load, RAG, LLM, upsert, Pearson, snapshot."""

from __future__ import annotations

import csv
import io
from typing import Any

import db
import llm_client
import rag_client
from config import get_settings
from loaders import load_upload
from logging_setup import log_with_correlation
from pearson import correlate, normalize_day

_CSV_HINTS = {"date", "sleep_hours", "productivity_score", "meeting_hours", "focus_hours"}


def parse_structured_csv(text: str) -> list[dict[str, Any]]:
    """Read a headered CSV when it looks like daily metrics. Other text returns []."""
    if not text or "date" not in text.splitlines()[0]:
        return []
    try:
        reader = csv.DictReader(io.StringIO(text))
    except csv.Error:
        return []
    names = {name.strip() for name in (reader.fieldnames or []) if name}
    if "date" not in names or not names & _CSV_HINTS:
        return []
    days: list[dict[str, Any]] = []
    for row in reader:
        cleaned = {str(key).strip(): value for key, value in row.items() if key}
        day = normalize_day(cleaned)
        if day is not None:
            days.append(day)
    return days


def merge_days(
    parsed: list[dict[str, Any]], inferred: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """LLM fields replace CSV fields for the same date. CSV fills gaps."""
    by_date: dict[str, dict[str, Any]] = {}
    for day in parsed:
        by_date[day["date"]] = dict(day)
    for day in inferred:
        current = by_date.get(day["date"], {"date": day["date"]})
        current.update(day)
        by_date[day["date"]] = current
    return [by_date[key] for key in sorted(by_date)]


def _insights(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if snapshot is None:
        return {"narrative": "", "inferred_facts": [], "llm_used": False}
    return {
        "narrative": snapshot.get("narrative") or "",
        "inferred_facts": snapshot.get("inferred_facts") or [],
        "llm_used": bool(snapshot.get("llm_used")),
    }


async def build_view(user_id: str) -> dict[str, Any]:
    """Correlations from stored days plus the latest narrative."""
    rows = await db.list_metrics(user_id)
    snapshot = await db.latest_snapshot(user_id)
    insights = _insights(snapshot)
    return {
        "user_id": user_id,
        "pairs": correlate(rows),
        "narrative": insights["narrative"],
        "inferred_facts": insights["inferred_facts"],
        "llm_used": insights["llm_used"],
    }


async def ingest_file(
    *,
    user_id: str,
    filename: str,
    data: bytes,
    correlation_id: str,
) -> dict[str, Any]:
    """Load, infer, persist. LLM failure raises before any write."""
    text, image = load_upload(filename, data)
    log_with_correlation(
        correlation_id,
        "info",
        f"POST /ingest user_id={user_id} filename={filename}",
    )
    context = await rag_client.excerpts(
        user_id=user_id,
        query=text or filename,
        correlation_id=correlation_id,
    )
    inferred = await llm_client.infer(
        text=text,
        excerpts=context,
        user_id=user_id,
        correlation_id=correlation_id,
        image=image,
    )
    days = merge_days(parse_structured_csv(text), inferred["days"])
    stored = []
    for day in days:
        stored.append(await db.upsert_day(user_id, day))
    rows = await db.list_metrics(user_id)
    pairs = correlate(rows)
    settings = get_settings()
    snapshot = await db.insert_snapshot(
        {
            "user_id": user_id,
            "correlation_id": correlation_id,
            "pairs": pairs,
            "narrative": inferred["narrative"],
            "inferred_facts": inferred["inferred_facts"],
            "llm_used": True,
            "model_id": settings.LLM_MODEL_ID,
        }
    )
    log_with_correlation(
        correlation_id,
        "info",
        f"snapshot id={snapshot['_id']} rows_upserted={len(stored)}",
    )
    return {
        "rows_upserted": len(stored),
        "correlations": pairs,
        "insights": {
            "narrative": inferred["narrative"],
            "inferred_facts": inferred["inferred_facts"],
            "llm_used": True,
        },
        "llm_used": True,
        "snapshot_id": snapshot["_id"],
    }
