"""One POST /chat to the base Qwen3.5-4B container. Temperature stays 0.

Analytics does not load model weights. Invalid JSON is retried once.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx
from config import get_settings
from exceptions import InvalidInferenceJSONError, LLMTimeoutError, LLMUpstreamError
from logging_setup import log_with_correlation
from pearson import normalize_day


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
        raise InvalidInferenceJSONError("LLM JSON was not an object")
    return data


def parse_inference(text: str) -> dict[str, Any]:
    """Map model JSON onto days, narrative, and inferred_facts."""
    try:
        data = _extract_json(text)
    except InvalidInferenceJSONError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidInferenceJSONError("LLM JSON parse failed") from exc

    narrative = str(data.get("narrative") or "").strip()
    if not narrative:
        raise InvalidInferenceJSONError("narrative is required")
    facts = data.get("inferred_facts") or []
    days_raw = data.get("days") or []
    if not isinstance(facts, list) or not isinstance(days_raw, list):
        raise InvalidInferenceJSONError("days and inferred_facts must be lists")
    days = []
    for item in days_raw:
        if not isinstance(item, dict):
            continue
        day = normalize_day(item)
        if day is not None:
            days.append(day)
    return {
        "narrative": narrative,
        "inferred_facts": [str(item) for item in facts if str(item).strip()],
        "days": days,
    }


def _prompt(*, text: str, excerpts: str, temperature: float, model_id: str) -> str:
    return (
        f"Model: {model_id} base. Temperature: {temperature}.\n"
        "Describe the uploaded diary or schedule. Return JSON only, no markdown:\n"
        '{"days":[{"date":"YYYY-MM-DD","sleep_hours":0,"productivity_score":1,'
        '"meeting_hours":0,"focus_hours":0}],'
        '"narrative":"...","inferred_facts":["..."]}\n'
        "Copy dates and numbers from the upload. Omit a numeric field the file does not state. "
        "The narrative stays on this upload and says which measures rise together. "
        "Do not say that one measure caused another. "
        "A fact from the other documents goes in inferred_facts, and that sentence says it is not from this upload. "
        "Hours are 0 to 24. productivity_score is 1 to 10. narrative is English.\n"
        f"Uploaded text:\n{text.strip() or '(image only)'}\n"
        f"RAG excerpts for this user only:\n{excerpts.strip() or '(none)'}\n"
    )


def _content(prompt: str, image: bytes) -> str | list[dict[str, Any]]:
    if not image:
        return prompt
    encoded = base64.b64encode(image).decode("ascii")
    return [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:application/octet-stream;base64,{encoded}"},
        },
    ]


async def _post_chat(
    *,
    prompt: str,
    user_id: str,
    correlation_id: str,
    image: bytes,
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
        "messages": [{"role": "user", "content": _content(prompt, image)}],
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
        log_with_correlation(correlation_id, "error", f"LLM service HTTP {response.status_code}")
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")
    if response.status_code != 200:
        log_with_correlation(correlation_id, "error", f"LLM service HTTP {response.status_code}")
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")
    data = response.json() or {}
    return str(data.get("response") or "")


async def infer(
    *,
    text: str,
    excerpts: str,
    user_id: str,
    correlation_id: str,
    image: bytes = b"",
) -> dict[str, Any]:
    """Call POST /chat once. A second call happens only when the JSON is invalid."""
    settings = get_settings()
    prompt = _prompt(
        text=text,
        excerpts=excerpts,
        temperature=settings.LLM_TEMPERATURE,
        model_id=settings.LLM_MODEL_ID,
    )
    last_error: Exception | None = None
    for attempt in (1, 2):
        raw = await _post_chat(
            prompt=prompt,
            user_id=user_id,
            correlation_id=correlation_id,
            image=image,
        )
        try:
            return parse_inference(raw)
        except InvalidInferenceJSONError as exc:
            last_error = exc
            log_with_correlation(correlation_id, "warning", f"LLM JSON invalid — retry {attempt}")
    log_with_correlation(correlation_id, "error", "LLM JSON invalid after retry")
    raise LLMUpstreamError(f"invalid JSON after retry: {last_error}")
