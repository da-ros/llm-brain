## Purpose

The shield-service capability is the premium Privacy & Scam Shield: it
accepts pasted email, SMS, or message text, an image, or a short video.
Heuristics and embedding similarity are evidence. Qwen3.5-4B reasons about
that evidence and states the scam likelihood. Alerts are explainable and
stored per user.

## ADDED Requirements

### Requirement: Shield service health endpoint

The Shield Service SHALL expose an unauthenticated health endpoint that
reports liveness without secrets.

#### Scenario: Service is running

- **GIVEN** the Shield Service process is up
- **WHEN** a client sends `GET /health`
- **THEN** the system responds HTTP 200 with `status` equal to `"ok"` and `service` equal to `"shield-service"`

### Requirement: Correlation ID propagation

The Shield Service SHALL propagate `X-Request-ID` on every inbound HTTP
request and every outbound call to RAG and the LLM Service, and SHALL
include that id in structured logs.

#### Scenario: Inbound header present

- **GIVEN** a request includes `X-Request-ID`
- **WHEN** the Shield Service handles the request
- **THEN** the same id is sent on outbound RAG headers and appears in every log line for that request

#### Scenario: Inbound header missing

- **GIVEN** a request has no `X-Request-ID`
- **WHEN** the Shield Service handles the request
- **THEN** the service generates a UUID, uses it for the rest of the hop, and returns it on the response

### Requirement: Premium-only access to Shield

Scan, incident listing, and guidelines-for-user data SHALL run only for
authenticated premium users. Free-tier users SHALL NOT obtain scan results
or persist incidents.

#### Scenario: Premium user is accepted

- **GIVEN** the caller is an authenticated user with `subscription_tier` equal to `"premium"`
- **WHEN** a scan request is received
- **THEN** the Shield Service processes the request for that `user_id` only

#### Scenario: Free user is rejected

- **GIVEN** the caller has `subscription_tier` equal to `"free"`
- **WHEN** a scan request is received
- **THEN** the Shield Service responds HTTP 403 and does not write a `shield_incidents` document

### Requirement: Multimodal scan reasoned by the LLM

On each scan the Shield Service SHALL accept pasted text (`source` of
`email`, `sms`, or `message`), an image, or a short video. An image SHALL
be OCR’d before heuristics. The heuristic pack SHALL run on pasted text
and on that OCR string. The service SHALL cosine-compare a RAG embedding
of that text (and of the image or video) against the labeled corpus, and
SHALL call the LLM Service (`POST /chat`, Qwen3.5-4B base, temperature 0)
with the OCR text, the evidence, and the media. The model's `likelihood`, `alert`, `severity`, `summary`,
and `rationale` are the verdict. The service SHALL NOT train a supervised
fraud model, SHALL NOT open Chroma directly, and SHALL NOT treat a
heuristic-only result as a successful scan.

#### Scenario: Text phishing is sent to the LLM

- **GIVEN** a premium user and message text that matches at least one high heuristic
- **WHEN** `POST /scan` is called with that text and `source` of `email`, `sms`, or `message`
- **THEN** the system calls the LLM Service, responds HTTP 200 with `llm_used` equal to true, and `reasons` includes at least one `type` equal to `"heuristic"` and one `type` equal to `"llm"`

#### Scenario: Image is OCR'd before the verdict

- **GIVEN** a premium user and an image of a message within the size cap
- **WHEN** `POST /scan` is called with `source` equal to `"image"`
- **THEN** the system OCRs the image, runs heuristics on the OCR text, calls the LLM Service with that text and the image, and responds HTTP 200 with `llm_used` equal to true, a numeric `likelihood`, and a reason that records the OCR step

#### Scenario: Video is reasoned without OCR

- **GIVEN** a premium user and a video file within the size cap
- **WHEN** `POST /scan` is called with `source` equal to `"video"`
- **THEN** the system does not OCR the video, embeds it, calls the LLM Service with the bytes, and responds HTTP 200 with `llm_used` equal to true and a numeric `likelihood`

#### Scenario: LLM marks a ham message safe

- **GIVEN** a premium user, a benign text fixture, and an LLM response with `alert` false
- **WHEN** `POST /scan` is called
- **THEN** the system responds HTTP 200 with `alert` equal to false and does not insert a `shield_incidents` row, even if a heuristic id is listed in `reasons`

#### Scenario: LLM marks a scam

- **GIVEN** a premium user and an LLM response with `alert` true and `severity` of `"medium"` or `"high"`
- **WHEN** `POST /scan` completes
- **THEN** the HTTP 200 body has `alert` equal to true and a non-empty `summary`

#### Scenario: Missing content is rejected

- **GIVEN** a premium user
- **WHEN** `POST /scan` is called with no text and no file, an invalid `source`, or a file over 20 MB
- **THEN** the system responds HTTP 422, does not call the LLM Service, and does not persist an incident

#### Scenario: LLM failure does not persist an alert

- **GIVEN** the LLM Service returns 5xx, times out, or returns JSON that is still invalid after one retry
- **WHEN** `POST /scan` is called
- **THEN** the Shield Service responds HTTP 502 or 504, does not persist an alert, and logs the correlation id

#### Scenario: Embed failure still asks the LLM

- **GIVEN** RAG `POST /embed` returns 5xx or times out and the LLM Service is healthy
- **WHEN** `POST /scan` is called with text or media
- **THEN** the system still calls the LLM, includes a reason `embedding_unavailable`, and returns the model's verdict

### Requirement: Explainability on every scan

Every 200 scan response SHALL include `reasons[]` describing which
heuristics fired, the nearest corpus item when an embedding was obtained,
and the LLM rationale, even when `alert` is false.

#### Scenario: Reasons present on a safe scan

- **GIVEN** a successful scan with `alert` false
- **WHEN** the 200 response is returned
- **THEN** `reasons` includes an item with `type` equal to `"llm"` and, when RAG embed succeeded, an embedding nearest-neighbour

### Requirement: Alert incidents are persisted and isolated

When `alert` is true the service SHALL insert a `shield_incidents` document
with `user_id`, `source`, `severity`, `summary`, `reasons`, `correlation_id`,
and `created_at`. `GET /incidents` SHALL return only the caller's alerts in
the Frame 7 envelope `{ incidents: [{ id, created_at, severity, summary, source }] }`.
Cross-user access SHALL NOT reveal that a resource exists. Duplicate
`correlation_id` retries SHALL not insert a second alert.

#### Scenario: Alert is stored

- **GIVEN** a scan that returns `alert` true
- **WHEN** the 200 response is sent
- **THEN** MongoDB contains one `shield_incidents` document for that `correlation_id` and `user_id`

#### Scenario: List matches Frame 7 contract

- **GIVEN** an authenticated premium user with at least one alert
- **WHEN** they send `GET /incidents`
- **THEN** the system responds HTTP 200 with `incidents` as an array of objects each containing `id`, `created_at`, `severity`, `summary`, and `source`

#### Scenario: Empty list is valid

- **GIVEN** an authenticated premium user with no alerts
- **WHEN** they send `GET /incidents`
- **THEN** the system responds HTTP 200 with `incidents` equal to `[]`

#### Scenario: Cross-user incident is hidden

- **GIVEN** an authenticated premium user
- **WHEN** they request another user's incident by id
- **THEN** the system responds HTTP 404 without revealing that the resource exists

#### Scenario: Duplicate correlation id is idempotent

- **GIVEN** an alert for a correlation id already exists
- **WHEN** the same scan is retried with that `X-Request-ID`
- **THEN** the system does not insert a second document and returns the stored result

### Requirement: Responsible-use guidelines

The Shield Service SHALL expose static English responsible-use guidelines
without secrets. The text SHALL state that scans are assistive, not a
guarantee, and that the MVP uses heuristics, embedding similarity, and
multimodal LLM reasoning on test text, images, and short videos.

#### Scenario: Guidelines are public to premium callers

- **GIVEN** an authenticated premium user
- **WHEN** they send `GET /guidelines`
- **THEN** the system responds HTTP 200 with a non-empty English `text` field and no secrets
