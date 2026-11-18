## Tasks

### A. Evidence index (already on disk)

- [x] A.1 Copy the five real Nora Vega training logs (v1–v5) into `thesis/evidence/finetune/logs/`. Leave the September `user1` pytest logs out. (≤2h)
- [x] A.2 Copy the on-device manifest tagged `qwen3.5-4b-lora-v5` to `thesis/evidence/finetune/pack-manifest.json`. Do not copy the GGUF. (≤2h)
- [x] A.3 Write `thesis/evidence/finetune/README.md` with the job table, the v5 batch sha256, and the mock-log exclusion. (≤2h)
- [x] A.4 Write `thesis/evidence/environment.md` for the checkout that created the index. State that the training log has no git SHA. (≤2h)
- [x] A.5 Write `thesis/evidence/acceptance-matrix.csv` with `pending` on every KPI row and `real` only on the recorded v5 training log. (≤2h)

### B. Corpus and protocol

- [x] B.1 Fill `thesis/evidence/corpus/manifest.csv` with document id, format, size or duration, provenance, anonymization, and split (`train` or `eval`). (≤2h)
- [x] B.2 Write `thesis/evidence/corpus/eval-queries.jsonl`. Exact copies of a v5 training sentence stay in the file and stay out of the Precision@3 mean. (≤2h)
- [x] B.3 Confirm `thesis/evidence/protocol.md` against the machine used for the measured runs. Three replies per prompt. (≤2h)

### C. Measured runs

- [x] C.1 Ingestion: one JSONL row per document (correlation id, format, status, triple count, error). Kind `real`. (≤2h)
- [x] C.2 Retrieval: for each eval query, store the ranked ids, list length, and relevance of the first three. Compute Precision@3 from those rows. (≤2h)
- [x] C.3 Generation: `base` and `base-rag` on the same prompts. Store complete-response time only. Three replies per prompt. (≤2h)
- [x] C.4 Grounding: human label per answer, with the cited source id. (≤2h)
- [x] C.5 `adapter-v5` is the host probe that loads the adapter. Do not use `FakeEngine`. (≤2h)
- [x] C.6 Shield: labeled examples, predicted label, and whether it matched. (≤2h)
- [x] C.7 Analytics: input series, expected r, returned r. (≤2h)

### D. Phone timing

- [x] D.1 Phone elapsed time for the v5 pack is out of this round. Do not write `handset.md`. (≤2h)

### E. Screenshots

- [x] E.1 Add the web and phone captures under `thesis/evidence/screenshots/`. Name the screen in the filename. (≤2h)

### F. Documentation

- [x] F.1 Write `output/documents/protocol-index.md` pointing at `thesis/evidence/` and at `docs/architecture/current-runtime.md`. (≤2h)
- [x] F.2 The open rows are filled. Chapters 3.1, 3.2, 3.3, and 3.4 may be drafted from this pack and `docs/architecture/current-runtime.md`. (≤2h)
