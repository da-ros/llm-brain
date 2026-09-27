"""Deterministic heuristic pack. Evidence only — never the verdict."""

from __future__ import annotations

import re

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "urgency",
        re.compile(
            r"act now|immediately|account suspended|within 24 hours|urgente",
            re.I,
        ),
    ),
    (
        "credential",
        re.compile(
            r"verify password|confirm ssn|one-time pin|update billing|verifique su cuenta",
            re.I,
        ),
    ),
    (
        "money",
        re.compile(r"gift card|wire transfer|bitcoin|wallet address", re.I),
    ),
    (
        "short_url",
        re.compile(r"(?:https?://)?(?:bit\.ly|t\.co|tinyurl(?:\.com)?|lnkd\.in)\b", re.I),
    ),
    (
        "prize",
        re.compile(r"lottery|you have won|claim your prize|premio", re.I),
    ),
)

_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_LOOKALIKE = ("paypa1", "g00gle", "micros0ft", "app1e")


def _host(url: str) -> str:
    rest = url.split("://", 1)[-1]
    return rest.split("/", 1)[0].split("?", 1)[0].lower()


def run_heuristics(text: str) -> list[str]:
    """Return stable heuristic ids that fire on this text. Order is fixed."""
    if not (text or "").strip():
        return []
    fired: list[str] = []
    for heuristic_id, pattern in _RULES:
        if pattern.search(text):
            fired.append(heuristic_id)
    hosts = [_host(match.group(0)) for match in _URL.finditer(text)]
    if any(token in host for host in hosts for token in _LOOKALIKE):
        fired.append("lookalike_host")
    return fired
