## Why

Chapters 3.1 and 3.3 of the thesis need one recorded alpha round. The service
code and the mocked pytest suite describe behavior. They do not contain
Precision@3, response times, or grounding judgments. This round does not
record a phone elapsed time.
One real adapter already exists and has to be the personalized condition of
that round.

## What Changes

- Define the alpha round as an evidence pack under `thesis/evidence/`.
- Bind the personalized condition to `qwen3.5-4b-lora-v5` for Nora Vega
  (`user_id` `57eec20b-9ee6-4e75-bc87-1668a8e5f8b6`).
- Separate that real training history from the September 2026 `user1` pytest logs.
- Define the compared configurations, the metrics, and the mock-versus-real label.
- Leave service behavior unchanged. This frame records and prescribes the
  round. It does not retune the model or change retrieval.

## Capabilities

### New Capabilities

- `alpha-validation`: The evidence pack for the alpha round, including which
  runs count as measurements and which files a thesis sentence may cite.

### Modified Capabilities

None. Product requirements from Frames 1–8 and 10 stay as they are.

## Impact

- Adds `thesis/evidence/` and this frame's `output/documents/protocol-index.md`.
- No API, service, or client change.
- Weights, raw personal documents, `.env`, and Chroma dumps stay gitignored
  under `data/`.

## Context from Frames 1–8 and 10

- **Frame 1 and 1.1.** The API Router on port 8000 is the only client entry.
  Passwords are PBKDF2-HMAC-SHA256. The running map is
  `docs/architecture/current-runtime.md`.
- **Frame 4.** Port 8003 is a host process serving base Qwen3.5-4B.
  Port 8004 is the host fine-tune process. The v5 job completed on
  16 November 2026 (8 epochs, final loss 0.0082, 27 triples).
- **Frame 2.** Ingestion writes triples JSONL. The v5 batch is the training
  set and is excluded from evaluation queries.
- **Frame 3.** Retrieval returns `RAG_TOP_K` items, default 8. Precision@3
  uses the first three. Fernet covers chunk text and a ciphertext copy of
  each vector. The index keeps raw floats.
- **Frame 5.** Premium chat runs `reason_graph`. `learn_graph` does not call
  `POST /train` by itself. Training stays a manual trigger.
- **Frames 6, 7, and 8.** Simulator, Life Analytics, and Shield are measured
  on their own labeled inputs. They are not inferred from chat tests.
- **Frame 10.** The phone runtime is `llama.rn`. The Q4 pack tagged
  `qwen3.5-4b-lora-v5` is built. `services/finetune/experiments/on-device-q4.md`
  records that a handset timing was not taken. `FakeEngine` (40 ms, 12 tokens)
  is a test double.

## Output

```
thesis/evidence/          # numbers the thesis may cite
output/documents/
└── protocol-index.md     # pointer from this frame to that pack
```

No new architecture diagram. Frames 1–8 and 10 already hold the diagrams.
This frame produces tables.

## Execution Order

Frame 9 runs after Frames 1, 1.1, 2, 3, 4, 5, 6, 7, 8, and 10. The v5
training run already happened. This frame indexes it, and the measurement
pack is filled. Thesis chapters 3.1, 3.2, 3.3, and 3.4 are written from
`thesis/evidence/` and `docs/architecture/current-runtime.md`.
