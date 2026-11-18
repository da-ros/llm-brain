## Context

See proposal.md. Frames 1–8 and 10 are implemented. Their historical text
still describes a containerized LLM and the Neural Engine in places. The
running system is `docs/architecture/current-runtime.md`. This frame does
not edit those services. It defines the round that chapters 3.1 and 3.3 cite.

The personalized model already exists. Job `ft-job-56f3ab60` completed on
16 November 2026 for Nora Vega and produced `qwen3.5-4b-lora-v5`. Versions
v1 through v4 of the same account are earlier real jobs. The September
`user1` logs are pytest.

## Goals / Non-Goals

**Goals:**

- One evidence pack a later draft can cite without reading `data/` or the test suite.
- A fixed personalized condition: adapter v5 and the Q4 pack tagged v5.
- Explicit pending rows for measurements that have not been run.
- A train/eval split that keeps the 27 v5 triples out of the queries.

**Non-Goals:**

- Changing RAG Top-k, the host model, or the phone engine.
- Retraining v5, or treating its training loss as a held-out score.
- Publishing weights, personal documents, or `.env`.
- Counting `FakeEngine` or a green pytest run as a KPI.

## Decisions

### 1. The evidence pack is the only numeric source

**Decision:** `thesis/evidence/` holds the environment snapshot, the corpus
manifest, the run sheets, the copied training logs, the pack manifest, the
screenshots, and the acceptance matrix. `data/` stays gitignored.

**Alternatives considered:**

- Letting a model read the repository and write chapter 3.3. Rejected. The
  mocked tests and the stale architecture pages would be copied in as results.
- Committing `data/training_logs/` as-is. Rejected. That directory also
  contains the pytest logs, and the ignore rule exists so weights and personal
  files are not published. The pack copies only the five real logs.

### 2. Three configurations, one machine, one prompt set

**Decision:** Where a comparison is run, the hardware, the prompt, and the
decoding settings stay fixed. The three conditions are:

| Id | Condition | Weights | Retrieval |
|----|-----------|---------|-----------|
| `base` | Web free, or premium with RAG turned off | Base Qwen3.5-4B on port 8003 | No |
| `base-rag` | Premium through `reason_graph` | Same base weights | Yes, service default k = 8 |
| `adapter-v5` | The v5 adapter loaded by the host probe | `qwen3.5-4b-lora-v5` | No retrieved context. Digital Brain mode is `base-rag`, not this row |

The host process on port 8003 does not load the adapter. The probe is a
separate process. The phone pack exists and is not timed in this round.

**Alternatives considered:**

- Comparing v1–v5 against each other as the main result. Rejected for the
  thesis comparison. Those logs stay in the pack as the training history.
  v5 is the definitive adapter because the exported pack is tagged v5.

### 3. Metrics

**Decision:**

- Precision@3: relevant items among the first three of the ranked list.
  The list may be longer because `RAG_TOP_K` is 8.
- Complete-response time: from the request leaving the client to the full
  reply. Report the distribution, not a single hidden average. First-token
  latency is out of this round because `POST /chat` does not stream.
- Ingestion success: per file, format, status, triple count, correlation id.
- Grounding: a human label that the answer is supported by the cited source,
  with the source id stored on the row.
- Training: the copied log (hyperparameters, epochs, final loss, triple count).
  The loss is on the training triples. The laptop `adapter-v5` rows are a
  reproduction check on the same questions.
- Phone elapsed time is outside this round. `FakeEngine` stays a test double.

### 4. What is already recorded

Recorded as `real` in this change:

- Training logs v1–v5 for `57eec20b-9ee6-4e75-bc87-1668a8e5f8b6`.
- v5 batch identity: 27 lines, sha256
  `8d5f8f08f93cc24f314fdff196d8fd7cff9a5eb77e4b942a0a39dcb470c00295`.
- Pack manifest tag `qwen3.5-4b-lora-v5`, 2708804096 bytes, sha256
  `2110d3cc8c0db8e17b8f0e259a47f220dae9583f89bec6502b752c0738d6a81d`.
- Machine snapshot of the documentation checkout, which is not the same fact
  as the commit that trained v5. The training log does not record a git commit.

The ten screenshots are filed under `thesis/evidence/screenshots/`. They illustrate section 3.2.9. A time printed on the phone status screen is not a measured result.

## Data Flow

```
Nora Vega documents
        │
        ▼
ETL → triples JSONL ──► v5 batch (27 records) ──► LoRA v5 ──► Q4 pack
        │                                              │
        │                                              └── thesis/evidence/finetune/
        ▼
held-out queries (must not be those 27 records)
        │
        ├── base      → port 8003, no RAG
        ├── base-rag  → reason_graph → Top-k 8 → Precision@3 on the first 3
        └── adapter-v5 → host probe that loads the adapter
        │
        ▼
thesis/evidence/runs/*.jsonl   (each row: real | mock)
        │
        ▼
acceptance-matrix.csv  →  chapters 3.1 and 3.3
```

## Design Patterns & SOLID Principles

This frame adds no class and no service. The controls are methodological.

| Pattern | Where | Purpose |
|---------|--------|---------|
| Controlled comparison | The three condition ids | Hold hardware and prompts fixed while the weights and the retrieval path change |
| Explicit null | Pending matrix rows | A measurement that was not run stays visible |
| Separation of fixture and observation | `mock` vs `real` | Pytest and `FakeEngine` cannot be read as the round |

| Principle | Application |
|-----------|-------------|
| Single responsibility | The evidence pack stores observations. Service code keeps doing the work. Historical frame text keeps the design history |
| Open/closed | A new run appends a row. It does not rewrite v5 |
| Dependency inversion | Thesis sentences depend on the pack, not on whichever architecture page is open |

## Risks / Trade-offs

| Risk | Why it matters |
|------|----------------|
| 27 training triples and a final loss of 0.0082 | The loss can be memorization. It is not a held-out score |
| One account, one Mac (M4 Pro, 48 GB) | Results do not generalize past this alpha |
| Retrieval k is 8 while the metric is Precision@3 | The metric must say it scored the first three of a longer list |
| Training commit was not logged | The pack records the log timestamp and refuses to invent the SHA |
| A screen can show a rounded or averaged time | Section 3.2.9 uses the screenshots as figures. Measured times stay in `thesis/evidence/runs/` |

## Migration Plan

No runtime migration. Authors add screenshots and, after each real run,
append rows. Pending rows stay pending until then.

## Open Questions

- `adapter-v5` in this round is the host probe. The phone pack is not timed.
- A demo video was part of the old frame title. This round does not treat a
  video as a measurement.

## Current runtime

Cite `docs/architecture/current-runtime.md` for ports, the host LLM, and
`llama.rn`. Do not cite Frame 1 or Frame 10 design sentences that still say
Neural Engine, ExecuTorch, or an LLM container.
