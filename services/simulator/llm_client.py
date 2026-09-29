"""One POST /chat to the base Qwen3.5-4B container. Temperature stays 0.

The simulator does not load model weights. Invalid JSON is retried once.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from config import get_settings
from exceptions import InvalidScenarioJSONError, LLMTimeoutError, LLMUpstreamError
from logging_setup import log_with_correlation


def _prompt(
    *,
    question: str,
    variables: dict[str, float],
    excerpts: str,
    leaves: list[dict[str, Any]],
    temperature: float,
    model_id: str,
) -> str:
    leaf_lines = []
    ids = []
    for leaf in leaves:
        ids.append(leaf["id"])
        leaf_lines.append(
            f"- id={leaf['id']} leaf={leaf['leaf_id']} trace={' > '.join(leaf['trace'])}"
        )
    excerpt_block = excerpts.strip() or "(no RAG excerpts)"
    return (
        f"Model: {model_id} base. Temperature: {temperature}.\n"
        "You are the decision-support reasoner. Write one scenario per leaf.\n"
        "Return JSON only, no markdown, with this shape:\n"
        '{"scenarios":[{"id":"...","title":"...","outcome":"...","assumptions":["..."]}]}\n'
        f"LEAF_IDS: {', '.join(ids)}\n"
        f"Question: {question}\n"
        f"Variables: {json.dumps(variables, sort_keys=True)}\n"
        f"RAG excerpts:\n{excerpt_block}\n"
        "Leaves:\n" + "\n".join(leaf_lines)
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
        raise InvalidScenarioJSONError("LLM JSON was not an object")
    return data


def parse_scenarios(text: str, leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map model JSON onto the tree leaves. Raises InvalidScenarioJSONError."""
    try:
        data = _extract_json(text)
    except InvalidScenarioJSONError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidScenarioJSONError("LLM JSON parse failed") from exc

    rows = data.get("scenarios")
    if not isinstance(rows, list):
        raise InvalidScenarioJSONError("LLM JSON missing scenarios")
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row

    authored: list[dict[str, Any]] = []
    for leaf in leaves:
        row = by_id.get(leaf["id"])
        if row is None:
            raise InvalidScenarioJSONError(f"missing scenario {leaf['id']}")
        title = str(row.get("title") or "").strip()
        outcome = str(row.get("outcome") or "").strip()
        assumptions = row.get("assumptions")
        if not title or not outcome or not isinstance(assumptions, list):
            raise InvalidScenarioJSONError(f"incomplete scenario {leaf['id']}")
        cleaned = [str(item).strip() for item in assumptions if str(item).strip()]
        if not cleaned:
            raise InvalidScenarioJSONError(f"empty assumptions for {leaf['id']}")
        authored.append(
            {"id": leaf["id"], "title": title, "outcome": outcome, "assumptions": cleaned}
        )
    return authored


async def _post_chat(
    *,
    prompt: str,
    user_id: str,
    excerpts: str,
    correlation_id: str,
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
        "messages": [{"role": "user", "content": prompt}],
        "user_id": user_id,
        "tier": "premium",
        "context": excerpts or None,
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


async def reason_scenarios(
    *,
    question: str,
    variables: dict[str, float],
    excerpts: str,
    leaves: list[dict[str, Any]],
    user_id: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Call POST /chat once. A second call happens only when the JSON is invalid."""
    settings = get_settings()
    prompt = _prompt(
        question=question,
        variables=variables,
        excerpts=excerpts,
        leaves=leaves,
        temperature=settings.LLM_TEMPERATURE,
        model_id=settings.LLM_MODEL_ID,
    )
    last_error: Exception | None = None
    for attempt in (1, 2):
        text = await _post_chat(
            prompt=prompt,
            user_id=user_id,
            excerpts=excerpts,
            correlation_id=correlation_id,
        )
        try:
            return parse_scenarios(text, leaves)
        except InvalidScenarioJSONError as exc:
            last_error = exc
            log_with_correlation(
                correlation_id,
                "warning",
                f"LLM JSON invalid — retry {attempt}",
            )
    log_with_correlation(correlation_id, "error", "LLM JSON invalid after retry")
    raise LLMUpstreamError(f"invalid JSON after retry: {last_error}")
