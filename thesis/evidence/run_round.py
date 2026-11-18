"""Build the Nora Vega evidence rows that do not need a phone.

Retrieval uses the live RAG service. Generation uses the host LLM on port
8003 when that process is up. The adapter is not loaded by that process.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
ARCHIVE = Path(
    "/Volumes/MicronSSD/U/GenAI/llm-brain-docs/docs-memory/nora-vega/Nora_Vega_Personal_Archive"
)
KEY = Path(
    "/Volumes/MicronSSD/U/GenAI/llm-brain-docs/docs-memory/nora-vega/Nora_Vega_Evaluation_Key"
)
TRIPLES = ROOT / "data/triples/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6"
USER_ID = "57eec20b-9ee6-4e75-bc87-1668a8e5f8b6"
RAG = "http://127.0.0.1:8002"
LLM = "http://127.0.0.1:8003"


def _get(url: str, timeout: float = 120) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _post(url: str, payload: dict, timeout: float = 600) -> tuple[dict, int]:
    started = time.perf_counter()
    data = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode())
    return body, int((time.perf_counter() - started) * 1000)


def load_sources() -> dict[str, list[str]]:
    truth = json.loads((KEY / "ground_truth.json").read_text())
    return {fact["id"]: [Path(name).name for name in fact["sources"]] for fact in truth["facts"]}


def relevant_files(memory_ids: str, sources: dict[str, list[str]]) -> list[str]:
    if not memory_ids or memory_ids == "NONE":
        return []
    names: list[str] = []
    for memory_id in memory_ids.split("+"):
        for name in sources.get(memory_id, []):
            if name not in names:
                names.append(name)
    return names


def write_queries(sources: dict[str, list[str]]) -> list[dict]:
    rows = []
    with (KEY / "evaluation_questions.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            files = relevant_files(row["memory_ids"], sources)
            rows.append(
                {
                    "query_id": row["id"],
                    "question": row["question"],
                    "expected_answer": row["expected_answer"],
                    "memory_ids": row["memory_ids"],
                    "skill": row["skill"],
                    "relevant_ids": files,
                    "relevance_rule": (
                        "A retrieved item is relevant when its source filename is in relevant_ids. "
                        "An empty relevant_ids list is a negative control."
                    ),
                }
            )
    path = EVIDENCE / "corpus/eval-queries.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return rows


def write_manifest_and_ingest() -> None:
    counts: dict[str, dict] = {}
    for path in sorted(TRIPLES.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            triple = json.loads(line)
            meta = triple.get("metadata") or {}
            name = Path(str(meta.get("source_file") or "")).name
            slot = counts.setdefault(
                name,
                {
                    "correlation_id": path.stem,
                    "triple_count": 0,
                    "timestamp": meta.get("timestamp") or "",
                },
            )
            slot["triple_count"] += 1
            if meta.get("timestamp"):
                slot["timestamp"] = meta["timestamp"]

    manifest_rows = []
    ingest_rows = []
    with (KEY / "file_manifest.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = Path(row["relative_path"]).name
            found = counts.get(name)
            manifest_rows.append(
                {
                    "doc_id": name,
                    "relative_path": row["relative_path"],
                    "format": row["extension"],
                    "bytes": row["bytes"],
                    "sha256": row["sha256"],
                    "provenance": "Nora Vega personal archive, fictional, withheld from the evaluation key",
                    "anonymized": "fictional",
                    "split": "memory",
                    "notes": "Ingested into Nora's memory. Not an evaluation question.",
                }
            )
            ingest_rows.append(
                {
                    "correlation_id": found["correlation_id"] if found else "",
                    "doc_id": name,
                    "format": row["extension"],
                    "status": "success" if found else "missing",
                    "triple_count": found["triple_count"] if found else 0,
                    "timestamp": found["timestamp"] if found else "",
                    "error": "" if found else "no triples jsonl for this file",
                    "kind": "real",
                }
            )
    with (EVIDENCE / "corpus/manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)
    (EVIDENCE / "runs/ingest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ingest_rows), encoding="utf-8"
    )


def source_name(item: dict) -> str:
    meta = item.get("metadata") or {}
    raw = str(meta.get("source") or meta.get("source_file") or "")
    return Path(raw).name


def run_retrieval(queries: list[dict]) -> None:
    rows = []
    for query in queries:
        url = (
            RAG
            + "/search?"
            + urllib.parse.urlencode({"query": query["question"], "user_id": USER_ID, "k": 8})
        )
        started = time.perf_counter()
        payload = _get(url)
        elapsed = int((time.perf_counter() - started) * 1000)
        results = payload.get("results") or []
        ranked = [source_name(item) for item in results]
        relevant = set(query["relevant_ids"])
        top3 = ranked[:3]
        hits = [name in relevant for name in top3]
        rows.append(
            {
                "query_id": query["query_id"],
                "ranked_ids": ranked,
                "list_length": len(ranked),
                "top3": top3,
                "relevant_at_3": hits,
                "precision_at_3": round(sum(hits) / 3, 4),
                "relevant_ids": query["relevant_ids"],
                "search_ms": elapsed,
                "kind": "real",
                "repetition": 1,
            }
        )
    (EVIDENCE / "runs/retrieval.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    scored = [row["precision_at_3"] for row in rows if row["relevant_ids"]]
    controls = [row["precision_at_3"] for row in rows if not row["relevant_ids"]]
    mean = round(sum(scored) / len(scored), 4) if scored else None
    print(f"retrieval queries={len(rows)} mean_p3_with_labels={mean} controls={controls}")


def llm_up() -> bool:
    try:
        _get(LLM + "/health", timeout=3)
    except Exception:
        return False
    return True


def run_generation(queries: list[dict], repetitions: int = 1) -> None:
    if not llm_up():
        print("generation skipped: port 8003 is closed")
        return
    path = EVIDENCE / "runs/generation.jsonl"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    done = set()
    for line in existing.splitlines():
        if line.strip():
            row = json.loads(line)
            done.add((row["config"], row["query_id"], row["repetition"]))
    with path.open("a", encoding="utf-8") as handle:
        for repetition in range(1, repetitions + 1):
            for config in ("base", "base-rag"):
                for query in queries:
                    key = (config, query["query_id"], repetition)
                    if key in done:
                        continue
                    context = ""
                    sources: list[str] = []
                    if config == "base-rag":
                        url = (
                            RAG
                            + "/context?"
                            + urllib.parse.urlencode(
                                {"query": query["question"], "user_id": USER_ID}
                            )
                        )
                        injected = _get(url)
                        context = injected.get("context") or ""
                        sources = injected.get("sources") or []
                    body, total_ms = _post(
                        LLM + "/chat",
                        {
                            "messages": [{"role": "user", "content": query["question"]}],
                            "user_id": USER_ID,
                            "tier": "premium",
                            "context": context,
                            "max_new_tokens": 256,
                        },
                    )
                    row = {
                        "config": config,
                        "query_id": query["query_id"],
                        "repetition": repetition,
                        "total_ms": total_ms,
                        "response": body.get("response") or "",
                        "tokens_used": body.get("tokens_used"),
                        "source_ids": [Path(str(item)).name for item in sources],
                        "expected_answer": query["expected_answer"],
                        "relevant_ids": query["relevant_ids"],
                        "path": "llm-direct",
                        "kind": "real",
                    }
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
                    print(f"{config} {query['query_id']} rep {repetition} {total_ms} ms")


def main() -> None:
    sources = load_sources()
    queries = write_queries(sources)
    write_manifest_and_ingest()
    print(f"wrote {len(queries)} queries and the corpus manifest")
    run_retrieval(queries)
    run_generation(queries, repetitions=1)


if __name__ == "__main__":
    main()
