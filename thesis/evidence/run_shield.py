"""Score the labeled Shield corpus against the live scanner.

Expected labels are read from data/shield/corpus.jsonl before each call.
phishing and scam should alert. ham should not.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/shield/corpus.jsonl"
OUT = Path(__file__).resolve().parent / "runs/shield.jsonl"
USER_ID = "57eec20b-9ee6-4e75-bc87-1668a8e5f8b6"
URL = "http://127.0.0.1:8009/scan"


def main() -> None:
    rows = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        expected = item["label"]
        expected_alert = expected in {"phishing", "scam"}
        payload = {
            "user_id": USER_ID,
            "subscription_tier": "premium",
            "source": item["source"],
            "text": item["text"],
        }
        row = {
            "example_id": item["id"],
            "expected": expected,
            "expected_alert": expected_alert,
            "source": item["source"],
            "kind": "real",
        }
        data = json.dumps(payload).encode()
        request = urllib.request.Request(
            URL, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = json.loads(response.read().decode())
            predicted = bool(body.get("alert"))
            row.update(
                {
                    "predicted": predicted,
                    "likelihood": body.get("likelihood"),
                    "severity": body.get("severity"),
                    "summary": body.get("summary") or "",
                    "match": predicted == expected_alert,
                    "error": "",
                }
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            row.update(
                {
                    "predicted": None,
                    "likelihood": None,
                    "severity": "",
                    "summary": "",
                    "match": False,
                    "error": str(exc),
                }
            )
        rows.append(row)
        print(
            f"{row['example_id']} expected={expected} predicted={row['predicted']} match={row['match']}"
        )
    OUT.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    matched = sum(1 for row in rows if row["match"])
    print(f"shield {matched}/{len(rows)}")


if __name__ == "__main__":
    main()
