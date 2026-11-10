"""One record per calendar event.

A VEVENT stays together: title, New York time, place, and what it was about.
The clock in a UTC stamp is converted to America/New_York.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_NEW_YORK = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def event_triples(text: str) -> list[dict]:
    """Return one subject-predicate-object record for each VEVENT."""
    records: list[dict] = []
    for props in _vevents(_unfold(text)):
        record = _record(props)
        if record is not None:
            records.append(record)
    return records


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in {" ", "\t"} and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _unescape(value: str) -> str:
    chars: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            chars.append("\n" if nxt in {"n", "N"} else nxt)
            index += 2
            continue
        chars.append(value[index])
        index += 1
    return "".join(chars)


def _property(line: str) -> tuple[str, dict[str, str], str]:
    if ":" not in line:
        return "", {}, ""
    head, _, raw = line.partition(":")
    name, _, param_text = head.partition(";")
    params: dict[str, str] = {}
    for part in param_text.split(";") if param_text else []:
        key, _, val = part.partition("=")
        params[key.upper()] = val
    return name.upper(), params, _unescape(raw).strip()


def _vevents(lines: list[str]) -> list[list[tuple[str, dict[str, str], str]]]:
    blocks: list[list[tuple[str, dict[str, str], str]]] = []
    current: list[tuple[str, dict[str, str], str]] | None = None
    for line in lines:
        name, params, value = _property(line)
        if name == "BEGIN" and value.upper() == "VEVENT":
            current = []
            continue
        if name == "END" and value.upper() == "VEVENT" and current is not None:
            blocks.append(current)
            current = None
            continue
        if current is not None and name:
            current.append((name, params, value))
    return blocks


def _moment(value: str, params: dict[str, str]) -> datetime | None:
    raw = value.strip()
    if len(raw) == 8 and "T" not in raw:
        return datetime.strptime(raw, "%Y%m%d")
    if raw.endswith("Z"):
        moment = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=_UTC)
        return moment.astimezone(_NEW_YORK)
    if len(raw) < 15:
        return None
    parsed = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
    tzid = params.get("TZID")
    zone = ZoneInfo(tzid) if tzid else _NEW_YORK
    return parsed.replace(tzinfo=zone).astimezone(_NEW_YORK)


def _day(moment: datetime) -> str:
    return f"{_MONTHS[moment.month - 1]} {moment.day}, {moment.year}"


def _when(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return ""
    if start.tzinfo is None:
        return _day(start)
    start_clock = start.strftime("%H:%M")
    if end is None or end.tzinfo is None:
        return f"{_day(start)}, {start_clock} New York time"
    end_clock = end.strftime("%H:%M")
    if end.date() == start.date():
        return f"{_day(start)}, {start_clock}–{end_clock} New York time"
    return f"{_day(start)}, {start_clock} – {_day(end)}, {end_clock} New York time"


def _sentences(pieces: list[str]) -> str:
    finished: list[str] = []
    for piece in pieces:
        text = piece.strip()
        if not text:
            continue
        if finished and finished[-1][-1] not in ".!?":
            finished[-1] += "."
        finished.append(text)
    if finished and finished[-1][-1] not in ".!?":
        finished[-1] += "."
    return " ".join(finished)


def _record(props: list[tuple[str, dict[str, str], str]]) -> dict | None:
    fields: dict[str, tuple[dict[str, str], str]] = {}
    attendees: list[str] = []
    for name, params, value in props:
        if name == "ATTENDEE" and value:
            label = params.get("CN") or value.removeprefix("mailto:")
            if label and label not in attendees:
                attendees.append(label)
            continue
        if name not in fields and value:
            fields[name] = (params, value)
    summary = fields.get("SUMMARY", ({}, ""))[1]
    if not summary:
        return None
    start = _moment(fields["DTSTART"][1], fields["DTSTART"][0]) if "DTSTART" in fields else None
    end = _moment(fields["DTEND"][1], fields["DTEND"][0]) if "DTEND" in fields else None
    place = fields.get("LOCATION", ({}, ""))[1]
    about = " ".join(fields.get("DESCRIPTION", ({}, ""))[1].split())
    when = _when(start, end)
    pieces: list[str] = []
    if when and place:
        pieces.append(f"{when} at {place}")
    elif when:
        pieces.append(when)
    elif place:
        pieces.append(place)
    if about:
        pieces.append(about)
    if attendees:
        pieces.append(f"Invited: {', '.join(attendees)}")
    uid = fields.get("UID", ({}, summary))[1]
    return {
        "subject": summary,
        "predicate": "scheduled",
        "object": _sentences(pieces),
        "metadata": {"source notes": f"Calendar event {uid}"},
    }
