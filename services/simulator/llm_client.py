"""One POST /chat to the base Qwen3.5-4B container. Temperature stays 0.

The simulator does not load model weights. A batch that is not JSON is
retried once. A batch that omits leaves is followed by one call per missing leaf.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from config import get_settings
from exceptions import InvalidScenarioJSONError, LLMTimeoutError, LLMUpstreamError
from logging_setup import log_with_correlation

# Three scenarios with a title, an outcome, and assumptions do not fit in 256 tokens.
SCENARIO_MAX_NEW_TOKENS = 1024


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
        "Return JSON only, no markdown and no text before or after it, with this shape:\n"
        '{"scenarios":[{"id":"...","title":"...","outcome":"...","assumptions":["..."]}]}\n'
        "Copy each id exactly from LEAF_IDS. Do not use the leaf: name as the id.\n"
        "assumptions must be a JSON array of short strings. One sentence per field.\n"
        f"LEAF_IDS: {', '.join(ids)}\n"
        f"Question: {question}\n"
        f"Variables: {json.dumps(variables, sort_keys=True)}\n"
        f"RAG excerpts:\n{excerpt_block}\n"
        "Leaves:\n" + "\n".join(leaf_lines)
    )


def _prompt_one(
    *,
    question: str,
    variables: dict[str, float],
    excerpts: str,
    leaf: dict[str, Any],
    temperature: float,
    model_id: str,
) -> str:
    excerpt_block = excerpts.strip() or "(no RAG excerpts)"
    return (
        f"Model: {model_id} base. Temperature: {temperature}.\n"
        "Return one JSON object and nothing else:\n"
        '{"id":"...","title":"...","outcome":"...","assumptions":["..."]}\n'
        f'The id must be exactly "{leaf["id"]}".\n'
        f"Question: {question}\n"
        f"Variables: {json.dumps(variables, sort_keys=True)}\n"
        f"RAG excerpts:\n{excerpt_block}\n"
        f"Leaf: id={leaf['id']} leaf={leaf['leaf_id']} trace={' > '.join(leaf['trace'])}\n"
        "One sentence for the title, one for the outcome, and one assumption.\n"
    )


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()


def _loads_object(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(repaired)


def _extract_json(text: str) -> dict[str, Any]:
    raw = _strip_thinking(text)
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    data = _loads_object(raw)
    if isinstance(data, list):
        return {"scenarios": data}
    if not isinstance(data, dict):
        raise InvalidScenarioJSONError("LLM JSON was not an object")
    return data


def _assumption_list(row: dict[str, Any]) -> list[str]:
    raw = row.get("assumptions")
    if raw is None:
        raw = row.get("assumption")
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _scenario_rows(data: dict[str, Any], leaves: list[dict[str, Any]]) -> list[Any]:
    rows = data.get("scenarios")
    if isinstance(rows, list):
        return rows
    if data.get("title") or data.get("outcome"):
        return [data]
    keyed: list[dict[str, Any]] = []
    for leaf in leaves:
        row = data.get(leaf["id"])
        if isinstance(row, dict):
            keyed.append({"id": leaf["id"], **row})
    return keyed


def _authored_row(leaf: dict[str, Any], row: dict[str, Any]) -> dict[str, Any] | None:
    title = str(row.get("title") or "").strip()
    outcome = str(row.get("outcome") or "").strip()
    cleaned = _assumption_list(row)
    if not title or not outcome or not cleaned:
        return None
    return {"id": leaf["id"], "title": title, "outcome": outcome, "assumptions": cleaned}


def collect_scenarios(text: str, leaves: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep every leaf the model actually finished. Incomplete replies return less."""
    try:
        data = _extract_json(text)
    except (InvalidScenarioJSONError, json.JSONDecodeError, ValueError):
        return {}
    rows = _scenario_rows(data, leaves)
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in (row.get("id"), row.get("leaf_id"), row.get("leaf")):
            if key:
                by_id[str(key).strip().lower()] = row
    found: dict[str, dict[str, Any]] = {}
    for leaf in leaves:
        row = by_id.get(str(leaf["id"]).lower()) or by_id.get(str(leaf["leaf_id"]).lower())
        if row is None and len(leaves) == 1 and len(rows) == 1 and isinstance(rows[0], dict):
            row = rows[0]
        if row is None:
            continue
        authored = _authored_row(leaf, row)
        if authored is not None:
            found[leaf["id"]] = authored
    return found


def parse_scenarios(text: str, leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map model JSON onto the tree leaves. Raises InvalidScenarioJSONError."""
    try:
        _extract_json(text)
    except InvalidScenarioJSONError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidScenarioJSONError("LLM JSON parse failed") from exc
    found = collect_scenarios(text, leaves)
    authored: list[dict[str, Any]] = []
    for leaf in leaves:
        row = found.get(leaf["id"])
        if row is None:
            raise InvalidScenarioJSONError(f"missing scenario {leaf['id']}")
        authored.append(row)
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
        "max_new_tokens": SCENARIO_MAX_NEW_TOKENS,
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


async def _one_scenario(
    *,
    question: str,
    variables: dict[str, float],
    excerpts: str,
    leaf: dict[str, Any],
    user_id: str,
    correlation_id: str,
    temperature: float,
    model_id: str,
) -> dict[str, Any]:
    """Ask for a single leaf. One retry when that object is still unusable."""
    prompt = _prompt_one(
        question=question,
        variables=variables,
        excerpts=excerpts,
        leaf=leaf,
        temperature=temperature,
        model_id=model_id,
    )
    last_text = ""
    for attempt in (1, 2):
        call_prompt = prompt
        if attempt == 2:
            call_prompt = (
                f"{prompt}\nThe previous reply was rejected. "
                f'Return only the JSON object with id "{leaf["id"]}".'
            )
        last_text = await _post_chat(
            prompt=call_prompt,
            user_id=user_id,
            excerpts=excerpts,
            correlation_id=correlation_id,
        )
        found = collect_scenarios(last_text, [leaf])
        row = found.get(leaf["id"])
        if row is not None:
            return row
        snippet = " ".join(last_text.split())[:240]
        log_with_correlation(
            correlation_id,
            "warning",
            f"LLM JSON invalid — retry {attempt}: missing scenario {leaf['id']} | {snippet}",
        )
    raise LLMUpstreamError(f"invalid JSON for {leaf['id']}")


async def reason_scenarios(
    *,
    question: str,
    variables: dict[str, float],
    excerpts: str,
    leaves: list[dict[str, Any]],
    user_id: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """One batch call. Missing leaves are requested one at a time."""
    settings = get_settings()
    prompt = _prompt(
        question=question,
        variables=variables,
        excerpts=excerpts,
        leaves=leaves,
        temperature=settings.LLM_TEMPERATURE,
        model_id=settings.LLM_MODEL_ID,
    )
    text = await _post_chat(
        prompt=prompt,
        user_id=user_id,
        excerpts=excerpts,
        correlation_id=correlation_id,
    )
    authored = collect_scenarios(text, leaves)
    missing = [leaf for leaf in leaves if leaf["id"] not in authored]
    if missing:
        log_with_correlation(
            correlation_id,
            "warning",
            "LLM JSON incomplete — fetching " + ", ".join(leaf["id"] for leaf in missing),
        )
    for leaf in missing:
        authored[leaf["id"]] = await _one_scenario(
            question=question,
            variables=variables,
            excerpts=excerpts,
            leaf=leaf,
            user_id=user_id,
            correlation_id=correlation_id,
            temperature=settings.LLM_TEMPERATURE,
            model_id=settings.LLM_MODEL_ID,
        )
    return [authored[leaf["id"]] for leaf in leaves]
