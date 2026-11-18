## Purpose

Records the alpha round so a measured claim in the thesis cites a file in
the evidence pack, and so mocked tests cannot be reported as those measurements.

## ADDED Requirements

### Requirement: Evidence pack is the source of measured numbers

The alpha round SHALL keep measured results in `thesis/evidence/`. A result
that is not in that pack SHALL NOT be stated as a finding. Weights, raw
personal documents, secrets, and Chroma dumps SHALL stay outside that pack.

#### Scenario: A metric has no row

- **WHEN** a thesis draft states Precision@3, a latency, or a grounding judgment
- **THEN** the draft cites a file under `thesis/evidence/` that contains that value

#### Scenario: The value was never recorded

- **WHEN** the evidence pack has no row for a metric
- **THEN** the draft says the measurement is pending and does not invent a number

### Requirement: Training examples and evaluation queries are disjoint

The round SHALL keep the triples used to train `qwen3.5-4b-lora-v5` out of
the evaluation query set. The v5 batch
(`data/finetune_batches/57eec20b-9ee6-4e75-bc87-1668a8e5f8b6/6af7ffe6805d32e6f8fb9a12.jsonl`,
27 records, sha256 `8d5f8f08f93cc24f314fdff196d8fd7cff9a5eb77e4b942a0a39dcb470c00295`)
SHALL be treated as training data.

#### Scenario: An evaluation query repeats a training record

- **WHEN** an evaluation query or its expected answer is one of the 27 v5 training records
- **THEN** the query is rejected from the evaluation set and is not used for Precision@3 or grounding

### Requirement: Personalized condition is adapter v5

The personalized condition of this round SHALL be adapter
`qwen3.5-4b-lora-v5` for `user_id`
`57eec20b-9ee6-4e75-bc87-1668a8e5f8b6` (Nora Vega). The on-device pack cited
for that condition SHALL be the manifest tagged `qwen3.5-4b-lora-v5`.

#### Scenario: A later job exists

- **WHEN** a training log for the same user has a version newer than v5
- **THEN** the round still cites v5 unless the evidence pack is explicitly revised to name the newer version

### Requirement: Every result row declares real or mock

Each recorded result SHALL carry `real` or `mock`. The September 2026 logs
whose `user_id` is `user1` and whose dataset path is under a pytest temporary
directory SHALL be `mock`. The pytest suite SHALL be `mock`. The November 2026
jobs v1 through v5 for Nora Vega SHALL be `real` training runs.

#### Scenario: A pytest log is cited as a training result

- **WHEN** a draft uses a `user1` pytest training log as the fine-tune result
- **THEN** the draft is wrong, and the cited run remains `mock`

### Requirement: Retrieval metric uses the first three items

Precision@3 SHALL be computed on the first three items of the ranked list
the service returns. The service default `RAG_TOP_K` is 8. Changing that
default is outside this round. A Precision@3 row SHALL name the query id,
the three ids, and whether each was relevant.

#### Scenario: The service returns eight items

- **WHEN** a real retrieval returns eight ranked items
- **THEN** Precision@3 is scored on the first three only, and the row records that the list length was eight

### Requirement: Response time is the complete reply

The round SHALL record complete-response time of the host model only.
`POST /chat` does not stream, so first-token latency is not a metric of this
round. Phone elapsed time is not a metric of this round. The phone
`FakeEngine` values of 40 ms and 12 tokens SHALL NOT be recorded as a
measured reply time.

#### Scenario: Chat returns only the finished reply

- **WHEN** a real host reply is timed on `POST /chat`
- **THEN** the row stores the complete-response time and no first-token field

#### Scenario: A draft cites a phone elapsed time

- **WHEN** a thesis draft states an iPhone elapsed time for the v5 pack
- **THEN** the draft is outside this round, because the pack does not record one

### Requirement: Acceptance matrix distinguishes functional tests from the round

The acceptance matrix SHALL list each thesis objective with a status of
`pass`, `fail`, or `pending`, and a kind of `mock` or `real`. A passing
pytest SHALL NOT set a KPI row to `pass`.

#### Scenario: CI is green and Precision@3 was not run

- **WHEN** pytest succeeds and `thesis/evidence/runs/` has no retrieval rows
- **THEN** the functional row may be `pass` with kind `mock`, and the Precision@3 row stays `pending`

## MODIFIED Requirements

None. This capability is new.
