## Purpose

The analytics-service capability ingests a premium user's diary or schedule
(CSV, XLSX, DOCX, ICS, or an image), asks Qwen3.5-4B to infer life facts from that
file and the user's other context, aligns daily metrics, and computes at
least two Pearson correlations (sleep vs productivity, meetings vs focus)
persisted with the model's narrative.

## ADDED Requirements

### Requirement: Analytics service health endpoint

The Analytics Service SHALL expose an unauthenticated health endpoint that
reports liveness without secrets.

#### Scenario: Service is running

- **GIVEN** the Analytics Service process is up
- **WHEN** a client sends `GET /health`
- **THEN** the system responds HTTP 200 with `status` equal to `"ok"` and `service` equal to `"analytics-service"`

### Requirement: Correlation ID propagation

The Analytics Service SHALL propagate `X-Request-ID` on every inbound HTTP
request and every outbound call to RAG and the LLM Service, and SHALL
include that id in structured logs.

#### Scenario: Inbound header present

- **GIVEN** a request includes `X-Request-ID`
- **WHEN** the Analytics Service handles the request
- **THEN** the same id appears in every log line for that request and on the response

#### Scenario: Inbound header missing

- **GIVEN** a request has no `X-Request-ID`
- **WHEN** the Analytics Service handles the request
- **THEN** the service generates a UUID, uses it for the rest of the hop, and returns it on the response

### Requirement: Premium-only analytics

Analytics ingest and queries SHALL run only for authenticated premium users.
Free-tier users SHALL NOT write metrics or read correlations.

#### Scenario: Premium user is accepted

- **GIVEN** the caller is an authenticated user with `subscription_tier` equal to `"premium"`
- **WHEN** an ingest or correlations request is received
- **THEN** the Analytics Service processes the request for that `user_id` only

#### Scenario: Free user is rejected

- **GIVEN** the caller has `subscription_tier` equal to `"free"`
- **WHEN** an ingest or correlations request is received
- **THEN** the Analytics Service responds HTTP 403 and does not write `life_metrics` or `analytics_snapshots`

### Requirement: Diary and schedule ingest without OAuth

The Analytics Service SHALL accept a diary or schedule as CSV, XLSX, DOCX,
ICS, or an image (PNG, JPEG, WEBP). It SHALL load documents with a
LangChain document loader. An image SHALL be OCR’d by the image loader
before inference, and the OCR text plus the image SHALL be sent to the
LLM. It SHALL call the LLM Service so the model can infer daily life facts
from that text, from the image when present, and from that user's RAG
context. It SHALL NOT call Google OAuth or
any third-party calendar API. An empty or unreadable file SHALL be rejected
without writing metrics. A successful ingest SHALL set `llm_used` true.

#### Scenario: Structured diary CSV ingest

- **GIVEN** a premium user and a CSV with header `date,sleep_hours,productivity_score` and at least one valid row
- **WHEN** `POST /ingest` is called
- **THEN** the system calls the LLM Service, responds HTTP 200 with `rows_upserted` greater than 0 and `llm_used` equal to true, and stores daily points for that `user_id`

#### Scenario: Prose DOCX or XLSX diary

- **GIVEN** a premium user and a `.docx` or `.xlsx` that describes a diary or schedule in prose or loose columns, without the CSV header
- **WHEN** `POST /ingest` is called
- **THEN** the system calls the LLM Service with the loaded text and RAG context, responds HTTP 200, and stores the inferred daily fields the model returned

#### Scenario: Calendar ICS or spreadsheet

- **GIVEN** a premium user and an `.ics` export or a spreadsheet of meetings and focus blocks
- **WHEN** `POST /ingest` is called
- **THEN** the system responds HTTP 200 and upserts per-day `meeting_hours` and `focus_hours` inferred for that `user_id`

#### Scenario: Photo of a diary

- **GIVEN** a premium user and a PNG or JPEG of a diary page or a schedule
- **WHEN** `POST /ingest` is called
- **THEN** the system OCRs the image, calls the LLM Service with the OCR text and the image, and responds HTTP 200 with `llm_used` equal to true

#### Scenario: Unreadable file is rejected

- **GIVEN** a premium user and an empty file or a type other than csv, xlsx, docx, ics, png, jpeg, or webp
- **WHEN** `POST /ingest` is called
- **THEN** the system responds HTTP 422, does not call the LLM Service, and does not change existing metrics

#### Scenario: LLM failure does not write metrics

- **GIVEN** the LLM Service returns 5xx, times out, or returns JSON that is still invalid after one retry
- **WHEN** `POST /ingest` is called with a readable file
- **THEN** the Analytics Service responds HTTP 502 or 504 and does not change `life_metrics` or `analytics_snapshots`

### Requirement: Two Pearson correlations on daily series

After ingest the service SHALL align points by calendar date and compute
Pearson r for (1) `sleep_hours` vs `productivity_score` and (2)
`meeting_hours` vs `focus_hours`. When a pair has fewer than two aligned
dates, `r` SHALL be null and `status` SHALL be `"insufficient"`. The
service SHALL NOT use Monte Carlo or stochastic sampling.

#### Scenario: Both correlations computed

- **GIVEN** a premium user with at least two overlapping diary days and two overlapping calendar days
- **WHEN** `GET /correlations` is called
- **THEN** the response includes both pairs, each with `r` (number), `n` (integer ≥ 2), `status` equal to `"ok"`, and the aligned `points` used

#### Scenario: Insufficient sample

- **GIVEN** a premium user with fewer than two aligned days for a pair
- **WHEN** `GET /correlations` is called
- **THEN** that pair has `r` equal to null, `n` less than 2, and `status` equal to `"insufficient"`, and the other pair is still returned

#### Scenario: Deterministic r

- **GIVEN** the same stored daily points
- **WHEN** `GET /correlations` is called twice
- **THEN** both responses contain the same `r`, `n`, and `points` for each pair

### Requirement: LLM insights over the user's data

Besides Pearson, every successful ingest SHALL ask the LLM to produce an
English `narrative` and `inferred_facts` grounded in the uploaded file and
in RAG context for that `user_id`. `GET /insights` and the correlations
payload SHALL return the latest narrative for that user. The service SHALL
NOT invent a narrative without calling the LLM.

#### Scenario: Insights returned with correlations

- **GIVEN** a premium user with a successful ingest
- **WHEN** they send `GET /correlations` or `GET /insights`
- **THEN** the response includes a non-empty `narrative` and `llm_used` equal to true

#### Scenario: RAG context is part of the prompt

- **GIVEN** a premium user with indexed personal documents
- **WHEN** `POST /ingest` runs
- **THEN** the LLM request includes excerpts from that user's RAG search, not another user's documents

### Requirement: Metrics and snapshots are isolated by user

Every ingest SHALL upsert `life_metrics` keyed by `(user_id, date)` and
SHALL write an `analytics_snapshots` document with both correlation
results, the LLM narrative, `llm_used`, `correlation_id`, and
`generated_at`. Reads SHALL return only the caller's rows. Cross-user
access SHALL NOT reveal that a resource exists.

#### Scenario: Snapshot written after ingest

- **GIVEN** a successful diary or calendar ingest
- **WHEN** the 200 response is sent
- **THEN** MongoDB contains an `analytics_snapshots` document for that `user_id` and `correlation_id`

#### Scenario: User reads own metrics

- **GIVEN** an authenticated premium user with stored days
- **WHEN** they send `GET /metrics`
- **THEN** the system returns only daily points whose `user_id` matches the token

#### Scenario: Cross-user access is denied

- **GIVEN** an authenticated premium user
- **WHEN** they request another user's snapshot or metrics by id
- **THEN** the system responds HTTP 404 without revealing that the resource exists
