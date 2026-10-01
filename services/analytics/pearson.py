"""Sample Pearson r. Deterministic. No Monte Carlo."""

from __future__ import annotations

from typing import Any

PAIR_SPECS = (
    ("sleep_productivity", "sleep_hours", "productivity_score"),
    ("meetings_focus", "meeting_hours", "focus_hours"),
)

METRIC_FIELDS = ("sleep_hours", "productivity_score", "meeting_hours", "focus_hours")
HOUR_FIELDS = {"sleep_hours", "meeting_hours", "focus_hours"}


def pearson(xs: list[float], ys: list[float]) -> tuple[float | None, int, str]:
    """Pairwise-complete Pearson r, rounded to 4 decimals.

    n < 2 or zero variance → (None, n, "insufficient").
    """
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys, strict=False)]
    n = len(pairs)
    if n < 2:
        return None, n, "insufficient"
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    sum_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    sum_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if sum_x == 0 or sum_y == 0:
        return None, n, "insufficient"
    return round(numerator / (sum_x * sum_y) ** 0.5, 4), n, "ok"


def _number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if field in HOUR_FIELDS:
        if not 0 <= number <= 24:
            return None
    elif field == "productivity_score":
        if not 1 <= number <= 10:
            return None
    else:
        return None
    return number


def normalize_day(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Keep a YYYY-MM-DD and only the fields that fall in range."""
    date = str(raw.get("date") or "").strip()[:10]
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        return None
    day: dict[str, Any] = {"date": date}
    for field in METRIC_FIELDS:
        number = _number(raw.get(field), field)
        if number is not None:
            day[field] = number
    if len(day) == 1:
        return None
    return day


def correlate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build both pairs from stored daily rows."""
    pairs: dict[str, Any] = {}
    for name, x_field, y_field in PAIR_SPECS:
        aligned = [
            row for row in rows if row.get(x_field) is not None and row.get(y_field) is not None
        ]
        aligned.sort(key=lambda row: row["date"])
        r, n, status = pearson(
            [row[x_field] for row in aligned],
            [row[y_field] for row in aligned],
        )
        points = [
            {
                "date": row["date"],
                "x": row[x_field],
                "y": row[y_field],
                x_field: row[x_field],
                y_field: row[y_field],
            }
            for row in aligned
        ]
        pairs[name] = {"r": r, "n": n, "status": status, "points": points}
    return pairs
