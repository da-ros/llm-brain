"""Scan orchestration: OCR, heuristics, cosine, then one LLM verdict."""

from __future__ import annotations

import base64
from typing import Any

import db
import rag_client
from corpus import CorpusItem, load_corpus, nearest
from exceptions import EmbedTimeoutError, EmbedUpstreamError
from heuristics import run_heuristics
from logging_setup import log_with_correlation
from ocr import ocr_image

_gallery: list[CorpusItem] | None = None

SOURCES = {"email", "sms", "message", "image", "video"}


def reset_gallery() -> None:
    """Drop the cached corpus vectors (tests)."""
    global _gallery
    _gallery = None


async def warm_gallery(correlation_id: str) -> list[CorpusItem]:
    """Embed each corpus line once via RAG POST /embed and keep the vectors."""
    global _gallery
    if _gallery is not None:
        return _gallery
    items = load_corpus()
    cached: list[CorpusItem] = []
    for item in items:
        vector = await rag_client.embed(
            modality="text",
            text=item.text,
            correlation_id=correlation_id,
        )
        cached.append(
            CorpusItem(
                id=item.id,
                label=item.label,
                source=item.source,
                text=item.text,
                vector=tuple(vector),
            )
        )
    _gallery = cached
    log_with_correlation(correlation_id, "info", f"corpus cached count={len(cached)}")
    return cached


def _suffix(filename: str, source: str) -> str:
    lower = (filename or "").lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov"):
        if lower.endswith(ext):
            return ext
    return ".mp4" if source == "video" else ".png"


def decode_file(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except Exception:
        return b""


async def collect_evidence(
    *,
    pasted: str,
    source: str,
    file_bytes: bytes,
    filename: str,
    correlation_id: str,
) -> dict[str, Any]:
    """OCR (images only), heuristics, and cosine. Embed failure is not fatal."""
    ocr_text = ""
    reasons: list[dict[str, Any]] = []
    is_video = source == "video"
    if file_bytes and not is_video and (source == "image" or _looks_like_image(filename)):
        ocr_text = ocr_image(file_bytes, suffix=_suffix(filename, "image"))
        if ocr_text:
            reasons.append({"type": "ocr", "id": "ocr_text", "detail": ocr_text})
            log_with_correlation(correlation_id, "info", f"OCR chars={len(ocr_text)}")
        else:
            reasons.append({"type": "ocr", "id": "ocr_empty"})
            log_with_correlation(correlation_id, "info", "OCR empty")
    elif is_video:
        log_with_correlation(correlation_id, "info", "video scan — OCR skipped")

    heuristic_ids: list[str] = []
    for blob in (pasted, ocr_text):
        for heuristic_id in run_heuristics(blob):
            if heuristic_id not in heuristic_ids:
                heuristic_ids.append(heuristic_id)
    for heuristic_id in heuristic_ids:
        reasons.append({"type": "heuristic", "id": heuristic_id})
    log_with_correlation(correlation_id, "info", f"heuristics fired={heuristic_ids}")

    queries: list[list[float]] = []
    embedding_unavailable = False
    gallery: list[CorpusItem] = []
    try:
        gallery = await warm_gallery(correlation_id)
    except (EmbedTimeoutError, EmbedUpstreamError):
        embedding_unavailable = True
        log_with_correlation(correlation_id, "warning", "embedding_unavailable corpus")

    text_for_embed = "\n".join(part for part in (pasted.strip(), ocr_text.strip()) if part)
    if not embedding_unavailable and text_for_embed:
        try:
            queries.append(
                await rag_client.embed(
                    modality="text",
                    text=text_for_embed,
                    correlation_id=correlation_id,
                )
            )
        except (EmbedTimeoutError, EmbedUpstreamError):
            embedding_unavailable = True

    media_modality = ""
    if file_bytes and source == "image":
        media_modality = "image"
    elif file_bytes and source == "video":
        media_modality = "video"
    elif file_bytes and _looks_like_image(filename):
        media_modality = "image"
    if file_bytes and media_modality and not embedding_unavailable:
        try:
            queries.append(
                await rag_client.embed(
                    modality=media_modality,
                    payload=file_bytes,
                    correlation_id=correlation_id,
                )
            )
        except (EmbedTimeoutError, EmbedUpstreamError):
            embedding_unavailable = True

    neighbour = nearest(queries, gallery) if queries and gallery else None
    if embedding_unavailable:
        reasons.append({"type": "embedding", "id": "embedding_unavailable"})
    nearest_id = None
    nearest_score = None
    if neighbour is not None:
        item, score = neighbour
        nearest_id = item.id
        nearest_score = round(score, 4)
        reasons.append(
            {
                "type": "embedding",
                "id": item.id,
                "score": nearest_score,
                "label": item.label,
            }
        )
        log_with_correlation(
            correlation_id,
            "info",
            f"nearest corpus_id={item.id} score={nearest_score:.4f}",
        )
    return {
        "ocr_text": ocr_text,
        "reasons": reasons,
        "heuristic_ids": heuristic_ids,
        "nearest_id": nearest_id,
        "nearest_score": nearest_score,
        "embedding_unavailable": embedding_unavailable,
        "media_type": media_modality,
    }


def _looks_like_image(filename: str) -> bool:
    lower = (filename or "").lower()
    return lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def public_result(document: dict[str, Any]) -> dict[str, Any]:
    """Stored alert → the same JSON a fresh scan would return."""
    stored = document.get("result")
    if isinstance(stored, dict):
        return stored
    return {
        "alert": True,
        "likelihood": document.get("likelihood"),
        "severity": document.get("severity"),
        "summary": document.get("summary"),
        "reasons": document.get("reasons") or [],
        "llm_used": bool(document.get("llm_used")),
        "incident_id": str(document.get("_id") or ""),
    }


def list_item(document: dict[str, Any]) -> dict[str, Any]:
    created = document.get("created_at")
    stored = document.get("result") if isinstance(document.get("result"), dict) else {}
    reasons = document.get("reasons") or stored.get("reasons") or []
    rationale = str(stored.get("rationale") or "")
    if not rationale:
        for reason in reasons:
            if isinstance(reason, dict) and reason.get("type") == "llm":
                rationale = str(reason.get("detail") or "")
                break
    return {
        "id": str(document.get("_id") or ""),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
        "severity": document.get("severity"),
        "summary": document.get("summary"),
        "source": document.get("source"),
        "rationale": rationale,
        "reasons": reasons,
    }


async def persist_alert(
    *,
    user_id: str,
    correlation_id: str,
    source: str,
    verdict: dict[str, Any],
    reasons: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    document = {
        "user_id": user_id,
        "correlation_id": correlation_id,
        "source": source,
        "likelihood": verdict["likelihood"],
        "llm_used": True,
        "severity": verdict["severity"],
        "summary": verdict["summary"],
        "reasons": reasons,
        "result": result,
    }
    stored = await db.insert_incident(document)
    incident_id = str(stored["_id"])
    result["incident_id"] = incident_id
    if db.use_memory():
        db.memory().by_id[incident_id]["result"] = result
        db.memory().by_correlation[document["correlation_id"]]["result"] = result
    log_with_correlation(
        correlation_id,
        "info",
        f"persisted incident id={incident_id} correlation_id={correlation_id}",
    )
    return stored
