"""Deterministic decision tree over sleep, time, money, and health.

The tree only chooses 3-5 leaves and a node trace. Qwen3.5-4B writes the
title, outcome, and assumptions. There is no random sampling and no Monte Carlo.
"""

from __future__ import annotations

import re
from typing import Any

FAMILY_ORDER = ("sleep", "time", "money", "health")

FAMILY_KEYS: dict[str, tuple[str, ...]] = {
    "sleep": ("sleep_hours",),
    "time": ("meeting_hours_per_day", "focus_hours_per_day"),
    "money": ("monthly_spend",),
    "health": ("active_prescriptions",),
}

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sleep": ("sleep", "asleep", "slept", "insomnia", "fatigue", "tired"),
    "time": ("meeting", "meetings", "focus", "calendar", "schedule", "productivity"),
    "money": ("spend", "spending", "spent", "money", "budget", "invoice", "expense", "cost"),
    "health": ("prescription", "prescriptions", "medication", "medicine", "health", "pill"),
}


def detect_families(question: str, variables: dict[str, Any] | None) -> list[str]:
    """Families implied by the question or by supplied variable keys.

    Order follows FAMILY_ORDER so the same inputs always pick the same primary
    family. A question that names nothing still walks the sleep family.
    """
    text = (question or "").lower()
    provided = variables or {}
    found: list[str] = []
    for family in FAMILY_ORDER:
        named = any(re.search(rf"\b{re.escape(word)}\b", text) for word in _KEYWORDS[family])
        supplied = any(key in provided and provided[key] is not None for key in FAMILY_KEYS[family])
        if named or supplied:
            found.append(family)
    return found or ["sleep"]


def families_covered(families: list[str], variables: dict[str, Any] | None) -> bool:
    """True when every key of every detected family is already in the request."""
    if not variables:
        return False
    for family in families:
        for key in FAMILY_KEYS[family]:
            if variables.get(key) is None:
                return False
    return True


def default_values(settings: Any) -> dict[str, float]:
    """Canonical defaults: 7h sleep, 3h meetings, 4h focus, 0 spend, 0 prescriptions."""
    return {
        "sleep_hours": float(settings.DEFAULT_SLEEP_HOURS),
        "meeting_hours_per_day": float(settings.DEFAULT_MEETING_HOURS),
        "focus_hours_per_day": float(settings.DEFAULT_FOCUS_HOURS),
        "monthly_spend": float(settings.DEFAULT_MONTHLY_SPEND),
        "active_prescriptions": float(settings.DEFAULT_ACTIVE_PRESCRIPTIONS),
    }


def default_assumption(key: str, value: float) -> str:
    """Explicit assumption recorded whenever a fact was not in the request or RAG."""
    if key in {"sleep_hours", "meeting_hours_per_day", "focus_hours_per_day"}:
        shown = f"{value:g}h"
    elif key == "monthly_spend":
        shown = f"{value:g} (unknown)"
    else:
        shown = f"{value:g}"
    return f"No personal context was found for {key}; used default {shown}."


def resolve_variables(
    families: list[str],
    provided: dict[str, Any] | None,
    parsed: dict[str, Any] | None,
    settings: Any,
) -> tuple[dict[str, float], dict[str, str]]:
    """Client values win, then RAG parses, then defaults.

    Returns the numeric map and assumption text keyed by each defaulted variable.
    """
    defaults = default_values(settings)
    merged: dict[str, Any] = {}
    merged.update(parsed or {})
    for key, value in (provided or {}).items():
        if value is not None:
            merged[key] = value

    resolved: dict[str, float] = {}
    assumptions: dict[str, str] = {}
    needed: list[str] = []
    for family in families:
        needed.extend(FAMILY_KEYS[family])
    for key in needed:
        raw = merged.get(key)
        if raw is None:
            resolved[key] = defaults[key]
            assumptions[key] = default_assumption(key, defaults[key])
            continue
        try:
            resolved[key] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid variable {key}") from exc
    return resolved, assumptions


def _leaf(
    scenario_id: str,
    severity: str,
    family: str,
    leaf_id: str,
    trace: list[str],
) -> dict[str, Any]:
    return {
        "id": scenario_id,
        "severity": severity,
        "family": family,
        "leaf_id": leaf_id,
        "trace": list(trace),
    }


def _mandatory(family: str, variables: dict[str, float]) -> list[dict[str, Any]]:
    if family == "sleep":
        hours = variables["sleep_hours"]
        if hours < 7:
            optimistic = ("leaf:recover_sleep", ["sleep_lt_7", "leaf:recover_sleep"])
            pessimistic = ("leaf:fatigue_high", ["sleep_lt_7", "leaf:fatigue_high"])
        else:
            optimistic = ("leaf:rested", ["sleep_gte_7", "leaf:rested"])
            pessimistic = ("leaf:fatigue_risk", ["sleep_drop", "leaf:fatigue_risk"])
        baseline = ("leaf:sleep_baseline", ["sleep_eq_current", "leaf:sleep_baseline"])
    elif family == "time":
        meetings = variables["meeting_hours_per_day"]
        focus = variables["focus_hours_per_day"]
        if focus >= 4 and meetings <= 3:
            optimistic = ("leaf:deep_work", ["focus_gte_4", "leaf:deep_work"])
        else:
            optimistic = ("leaf:focus_recovered", ["meetings_cut", "leaf:focus_recovered"])
        if meetings > 3:
            pessimistic = ("leaf:focus_squeezed", ["meetings_gt_3", "leaf:focus_squeezed"])
        else:
            pessimistic = ("leaf:shallow_work", ["focus_drop", "leaf:shallow_work"])
        baseline = ("leaf:time_baseline", ["time_eq_current", "leaf:time_baseline"])
    elif family == "money":
        spend = variables["monthly_spend"]
        if spend > 0:
            optimistic = ("leaf:budget_relief", ["spend_cut", "leaf:budget_relief"])
            pessimistic = ("leaf:budget_pressure", ["spend_gt_0", "leaf:budget_pressure"])
        else:
            optimistic = ("leaf:spend_unknown", ["spend_eq_0", "leaf:spend_unknown"])
            pessimistic = (
                "leaf:budget_unknown_risk",
                ["spend_unknown", "leaf:budget_unknown_risk"],
            )
        baseline = ("leaf:money_baseline", ["money_eq_current", "leaf:money_baseline"])
    else:
        prescriptions = variables["active_prescriptions"]
        if prescriptions > 0:
            optimistic = ("leaf:meds_managed", ["rx_stable", "leaf:meds_managed"])
            pessimistic = ("leaf:meds_active", ["rx_gt_0", "leaf:meds_active"])
        else:
            optimistic = ("leaf:no_prescriptions", ["rx_eq_0", "leaf:no_prescriptions"])
            pessimistic = ("leaf:new_prescription_risk", ["rx_new", "leaf:new_prescription_risk"])
        baseline = ("leaf:health_baseline", ["health_eq_current", "leaf:health_baseline"])

    return [
        _leaf("optimistic", "optimistic", family, *optimistic),
        _leaf("baseline", "baseline", family, *baseline),
        _leaf("pessimistic", "pessimistic", family, *pessimistic),
    ]


def walk_tree(families: list[str], variables: dict[str, float]) -> list[dict[str, Any]]:
    """Three mandatory leaves plus up to two extras when several families are present.

    Cap is 5. The same families and numbers always produce the same traces.
    """
    ordered = [family for family in FAMILY_ORDER if family in families] or ["sleep"]
    leaves = _mandatory(ordered[0], variables)
    for family in ordered[1:3]:
        distinctive = _mandatory(family, variables)[2]
        leaves.append(
            _leaf(
                f"extra_{family}",
                "extra",
                family,
                distinctive["leaf_id"],
                distinctive["trace"],
            )
        )
    return leaves[:5]
