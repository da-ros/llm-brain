"""One POST /chat to the base Qwen3.5-4B container. Temperature stays 0.

Shield does not load model weights. Invalid JSON is retried once.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from config import get_settings
from exceptions import InvalidVerdictJSONError, LLMTimeoutError, LLMUpstreamError
from logging_setup import log_with_correlation

_SEVERITY = {"none", "medium", "high"}


def _prompt(
    *,
    pasted: str,
    ocr_text: str,
    heuristic_ids: list[str],
    nearest_id: str | None,
    nearest_score: float | None,
    embedding_unavailable: bool,
    temperature: float,
    model_id: str,
    threshold: float,
) -> str:
    neighbour = "unavailable" if embedding_unavailable else f"{nearest_id} cosine={nearest_score}"
    return (
        f"Model: {model_id} base. Temperature: {temperature}.\n"
        "You decide whether this item is a phishing or scam attempt.\n"
        "Heuristics and the nearest corpus neighbour are evidence. You may disagree.\n"
        "Return JSON only, no markdown:\n"
        '{"likelihood":0.0,"alert":false,"severity":"none","summary":"...","rationale":"..."}\n'
        "severity is none, medium, or high. likelihood is 0 to 1.\n"
        f"Suggested bands (you may depart): several heuristics or cosine>=0.90 → high; "
        f"one heuristic or cosine>={threshold} → medium; ham neighbour and no heuristics → none.\n"
        f"Pasted text:\n{pasted.strip() or '(none)'}\n"
        f"OCR text:\n{ocr_text.strip() or '(none)'}\n"
        f"Heuristic ids: {', '.join(heuristic_ids) or '(none)'}\n"
        f"Nearest corpus: {neighbour}\n"
    )


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise InvalidVerdictJSONError("LLM JSON was not an object")
    return data


def parse_verdict(text: str) -> dict[str, Any]:
    """Map model JSON onto the verdict. Raises InvalidVerdictJSONError."""
    try:
        data = _extract_json(text)
    except InvalidVerdictJSONError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidVerdictJSONError("LLM JSON parse failed") from exc

    try:
        likelihood = float(data["likelihood"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidVerdictJSONError("likelihood missing") from exc
    if not 0.0 <= likelihood <= 1.0:
        raise InvalidVerdictJSONError("likelihood out of range")
    if not isinstance(data.get("alert"), bool):
        raise InvalidVerdictJSONError("alert must be boolean")
    severity = str(data.get("severity") or "")
    if severity not in _SEVERITY:
        raise InvalidVerdictJSONError("severity invalid")
    summary = str(data.get("summary") or "").strip()
    rationale = str(data.get("rationale") or "").strip()
    if not summary or not rationale:
        raise InvalidVerdictJSONError("summary and rationale are required")
    return {
        "likelihood": likelihood,
        "alert": data["alert"],
        "severity": severity,
        "summary": summary,
        "rationale": rationale,
    }


def _content(
    prompt: str,
    *,
    media: bytes,
    media_type: str,
) -> str | list[dict[str, Any]]:
    if not media:
        return prompt
    encoded = base64.b64encode(media).decode("ascii")
    kind = "image_url" if media_type == "image" else "video_url"
    url_key = "image_url" if media_type == "image" else "video_url"
    return [
        {"type": "text", "text": prompt},
        {"type": kind, url_key: {"url": f"data:application/octet-stream;base64,{encoded}"}},
    ]


async def _post_chat(
    *,
    prompt: str,
    user_id: str,
    correlation_id: str,
    media: bytes,
    media_type: str,
) -> str:
    settings = get_settings()
    url = f"{settings.LLM_SERVICE_URL}/chat"
    log_with_correlation(
        correlation_id,
        "info",
        (
            f"LLM POST /chat {url} temperature={settings.LLM_TEMPERATURE} "
            f"model={settings.LLM_MODEL_ID}"
        ),
    )
    payload = {
        "messages": [
            {
                "role": "user",
                "content": _content(prompt, media=media, media_type=media_type),
            }
        ],
        "user_id": user_id,
        "tier": "premium",
        "temperature": settings.LLM_TEMPERATURE,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "LLM service timeout")
        raise LLMTimeoutError("LLM service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"LLM service error: {exc}")
        raise LLMUpstreamError(f"LLM service error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "LLM service HTTP 504")
        raise LLMTimeoutError("LLM service timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"LLM service HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")
    if response.status_code != 200:
        log_with_correlation(
            correlation_id,
            "error",
            f"LLM service HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")
    data = response.json() or {}
    return str(data.get("response") or "")


async def judge(
    *,
    pasted: str,
    ocr_text: str,
    heuristic_ids: list[str],
    nearest_id: str | None,
    nearest_score: float | None,
    embedding_unavailable: bool,
    user_id: str,
    correlation_id: str,
    media: bytes = b"",
    media_type: str = "",
) -> dict[str, Any]:
    """Call POST /chat once. A second call happens only when the JSON is invalid."""
    settings = get_settings()
    prompt = _prompt(
        pasted=pasted,
        ocr_text=ocr_text,
        heuristic_ids=heuristic_ids,
        nearest_id=nearest_id,
        nearest_score=nearest_score,
        embedding_unavailable=embedding_unavailable,
        temperature=settings.LLM_TEMPERATURE,
        model_id=settings.LLM_MODEL_ID,
        threshold=settings.SIMILARITY_THRESHOLD,
    )
    last_error: Exception | None = None
    for attempt in (1, 2):
        text = await _post_chat(
            prompt=prompt,
            user_id=user_id,
            correlation_id=correlation_id,
            media=media,
            media_type=media_type,
        )
        try:
            return parse_verdict(text)
        except InvalidVerdictJSONError as exc:
            last_error = exc
            log_with_correlation(
                correlation_id,
                "warning",
                f"LLM JSON invalid — retry {attempt}",
            )
    log_with_correlation(correlation_id, "error", "LLM JSON invalid after retry")
    raise LLMUpstreamError(f"invalid JSON after retry: {last_error}")
