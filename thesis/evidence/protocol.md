# Run sheet

Normative rules: `openspec/changes/objective-9-alpha-validation/design.md`.

## Order

1. Freeze this environment table for the commit under test.
2. Finish the corpus manifest. Mark each document `train` or `eval`.
3. Write evaluation queries from `Nora_Vega_Evaluation_Key`. Do not ingest that directory. The questions may ask about facts that also appear in the training triples. The question text and the answer key are not training examples.
4. The archive is already distilled. Record one ingest row per archive file. Do not ingest the evaluation key.
5. On the same prompts, run `base`, then `base-rag`. This round records three
   complete replies per prompt. If a call fails, record the error and continue.
   Do not silently retry into a successful row.
6. Run `adapter-v5` on a host probe that loads the adapter. This round does
   not time the phone pack.
7. Score Precision@3 on the first three retrieved items. An item counts as
   relevant when its source filename is one of the files listed for that
   question's memory ids in `ground_truth.json`. A question with no memory
   id (the phone-number control) has an empty relevant set, so every hit
   is irrelevant. Score grounding against the expected answer and, for
   `base-rag`, against those same source files. Score Shield and Analytics
   on their own labeled inputs.
8. Append rows under `runs/`. Update `acceptance-matrix.csv`. Leave a cell
   `pending` when the step did not happen.

## Labels

- `real` — a live model, a live retrieval index, or the recorded v5 training job.
- `mock` — pytest, `QWEN_MOCK`, `EMBEDDING_MOCK`, `LORA_MOCK`, or `FakeEngine`.

## Already done

The v5 training job and the Q4 pack manifest are filed under `finetune/`.
Do not train again in order to have a log.

## Train questions and exam questions

The v5 batch is 27 question-and-answer triples (`predicate` `was_answered`).
Fine-tuning is supposed to reproduce those answers. The archive facts are
therefore allowed to sit in both the memory index and the adapter.

The evaluation sheet is a different object. Its sentences are not in the
memory index. Four of them are the same sentence as a training triple
(`Q05`, `Q12`, `Q14`, `Q20`). Those four stay in the files and stay out of
the Precision@3 and grounding means (`in_precision_at_3` and
`in_grounding_kpi` are false). The other 18 are paraphrases of the training
questions. They remain in those means. `adapter-v5` on any of the 22 is a
reproduction check, not a test of unseen questions.

## This round

Recorded on this laptop, three replies per prompt. The reply text did not
change across the three passes. The times did.

- 23 archive files were already distilled (196 triples). No second upload.
- Precision@3 uses the first three items returned by `GET /search`. The
  service asks for 8 neighbors and then appends the rest of a matched note,
  so a row can be longer than 8.
- `fact_match` is a reading of the reply against `expected_answer`.
  `grounded` is true only for `base-rag` when that reading matches and at
  least one cited filename is in `relevant_ids`. `base` has no citation, so
  `grounded` stays false there.
- Analytics uses the eight days already stored for Nora. The expected r is
  `services/analytics/pearson.py` on those points.
- Shield uses `data/shield/corpus.jsonl`. A phishing or scam item should
  alert. A ham item should not.
- The simulator rows are the three Nora scenarios already stored on
  10 November 2026. Phone elapsed time is not part of this round.

## Not done

Nothing in the measurement pack. Chapters 3.1, 3.2, 3.3, and 3.4 are the
writing that follows.

## What closes each pending matrix row

A row stays `pending` until the file in `acceptance-matrix.csv` exists and
its rows are `real`. `QWEN_MOCK=true` or `EMBEDDING_MOCK=true` makes the row
`mock`, and a mock row does not close a KPI.

| Matrix check | Do this once, on the Mac, with the real models loaded |
|--------------|--------------------------------------------------------|
| Ingestion | The archive is already distilled. Write one line per archive file in `runs/ingest.jsonl`. Do not ingest the evaluation key. |
| Precision@3 | For each line in `corpus/eval-queries.jsonl`, call retrieval, keep the ranked ids, and mark which of the first three are relevant. One line per query in `runs/retrieval.jsonl`. Precision@3 is the mean of (relevant among the first three) / 3. |
| Base and base-rag timing | Same prompts. This round is one reply each, through `POST /chat` on port 8003. `base-rag` prepends `GET /context`. That is the host model plus the retrieved text. It is not the premium agents graph. |
| Adapter reproduction | Same prompts on a host probe that loads the adapter. These questions paraphrase the 27 training triples, so the adapter row is a reproduction check. |
| Grounding | On each generation row, set `grounded` to yes or no by reading the answer against the cited source. |
| Simulator | Copy each stored Nora scenario, with its assumptions, into `runs/simulator.jsonl`. |
| Analytics | One labeled series. Record the expected Pearson r and the r the service returns in `runs/analytics.jsonl`. |
| Shield | A handful of messages you already labeled as scam or not. Record expected, predicted, and match in `runs/shield.jsonl`. |
| Screenshots | The files named in `screenshots/README.md`. |

Chapter 3.1 can be drafted from this sheet, `environment.md`, and the corpus
manifest. Chapter 3.3 waits until the JSONL files above exist. A missing file
is written as pending, not as a number.
