# Thesis evidence

This directory is the only source of measured numbers for chapters 3.1, 3.3,
and 3.4. The rules are specified in
`openspec/changes/objective-9-alpha-validation/specs/alpha-validation/spec.md`.

How the system runs is `docs/architecture/current-runtime.md`. Frame proposals
keep older decisions. Do not cite those older sentences as the current runtime.

## Rules for a draft

- If a number is not in a file here, the sentence says the measurement is pending.
- Every result row is `real` or `mock`. Pytest and `FakeEngine` are `mock`.
- The 27 v5 triples are the training records. Four evaluation sentences repeat one of them and stay out of the Precision@3 mean.
- Do not copy weights, raw personal documents, `.env`, or Chroma data into this directory.

## What is here

| Path | Status |
|------|--------|
| `environment.md` | Snapshot of the checkout that created this index. Not the training commit |
| `protocol.md` | Run sheet |
| `acceptance-matrix.csv` | Measured rows recorded |
| `finetune/` | Real jobs v1–v5 and the v5 pack manifest. No weights |
| `corpus/` | 23 archive files and 22 evaluation questions |
| `runs/` | Ingest, retrieval, generation, shield, analytics, and simulator |
| `screenshots/` | Ten figures for section 3.2.9 |

## How to close the pending rows

Do these in order. After each one, set the matching row in
`acceptance-matrix.csv` to `pass` or `fail`. Leave it `pending` if the step
did not happen. Chapter 3.1 can be drafted from `protocol.md` and
`environment.md` before the runs. Chapter 3.3 waits until the rows below exist.

1. **Corpus.** Nora Vega already has 23 triple files under
   `data/triples/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6/`. Write
   `corpus/manifest.csv` from those files: id, format, size, provenance,
   anonymized yes or no, and `train` or `eval`. Copy no document text.
   The v5 batch of 27 records stays `train`.
2. **Queries.** Write the evaluation questions in `corpus/eval-queries.jsonl`.
   They ask the same facts as the 27 training triples, in the same or
   reworded sentences. Each line needs `query_id`, `question`,
   `expected_answer`, `relevant_ids`, and `training_relation`. Do not ingest
   the evaluation key.
3. **Ingest.** Re-run only the documents that are not already distilled.
   Append one line per file to `runs/ingest.jsonl`.
4. **Retrieval and generation.** With the stack up and `QWEN_MOCK=false`,
   ask each query as `base` (no RAG) and `base-rag` (retrieved context).
   Three replies per prompt. Record ranked ids and `total_ms` in
   `runs/retrieval.jsonl` and `runs/generation.jsonl`. Score Precision@3
   from the first three ids only.
5. **Grounding.** Read each `base-rag` answer and set `grounded` to true
   only when the cited source supports it.
6. **Adapter.** Load v5 on the laptop and ask the same questions with no
   retrieved context. That host probe is `adapter-v5`. This round does not
   time the phone pack.
7. **Shield and analytics.** One JSONL line per labeled example. The
   expected value is written before looking at the system output.
8. **Screenshots.** The list is `screenshots/README.md`.

## Personalized condition

Nora Vega, `user_id` `57eec20b-9ee6-4e75-bc87-1668a8e5f8b6`, adapter
`qwen3.5-4b-lora-v5`, job `ft-job-56f3ab60`.
