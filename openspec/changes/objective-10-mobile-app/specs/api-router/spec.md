## ADDED Requirements

### Requirement: On-device pack metadata

The API Router SHALL expose `GET /api/models/on-device` to an
authenticated caller. The pack SHALL be chosen from the token plan.
A client-supplied tier SHALL be ignored. The JSON SHALL include `id`,
`family`, `tier`, `quantization`, `parameters`, `filename`, `bytes`,
`sha256`, and `ready`. A free token SHALL receive `id`
`qwen3.5-4b-base-q4` and SHALL NOT receive `qwen3.5-4b-finetuned-q4`.
A premium token SHALL receive `qwen3.5-4b-finetuned-q4` for that token's
`user_id`, with `ready` true only when that user's weight file is present
and its size equals the manifest `bytes`. The `sha256` in the response
SHALL be the value stored in the manifest at export. The route SHALL NOT
read the weight file to recompute it. The phone checks that value after
download. When that user's pack is absent or the file size does not
match, `ready` SHALL be false. The route SHALL NOT return another
user's pack. The route SHALL NOT call the LLM container and SHALL NOT
publish Kafka.

#### Scenario: Free metadata is the base pack

- **GIVEN** an authenticated free-tier user and a ready base pack
- **WHEN** they send `GET /api/models/on-device`, including a query that asks for the premium pack
- **THEN** the Router responds HTTP 200 with `id` `qwen3.5-4b-base-q4`, `quantization` `Q4`, and `ready` true

#### Scenario: Premium metadata when the pack is missing

- **GIVEN** an authenticated premium user and no ready fine-tuned pack for that user
- **WHEN** they send `GET /api/models/on-device`
- **THEN** the Router responds HTTP 200 with `id` `qwen3.5-4b-finetuned-q4` and `ready` false

#### Scenario: Premium metadata is per user

- **GIVEN** a ready fine-tuned pack for user A and an authenticated premium token for user B
- **WHEN** user B sends `GET /api/models/on-device`
- **THEN** the Router does not return A's checksum or filename and `ready` is false

#### Scenario: No token

- **GIVEN** a request without a valid JWT
- **WHEN** the client sends `GET /api/models/on-device`
- **THEN** the Router responds HTTP 401

### Requirement: On-device pack download

The API Router SHALL expose `GET /api/models/on-device/file` to an
authenticated caller and stream that caller's ready pack. The response
SHALL be the weight bytes. `X-Request-ID` SHALL be accepted and logged
with the route. The log SHALL NOT include the file bytes. A free token
SHALL receive only the base pack. A premium token SHALL receive that user's fine-tuned pack when `ready`
is true. When that user's pack is not ready, the file route SHALL
respond HTTP 404 and SHALL NOT substitute the base pack or another
user's pack. The route SHALL NOT call the LLM container and SHALL NOT
publish Kafka. Existing `POST /api/chat` behavior for the web app SHALL
stay unchanged.

#### Scenario: Free download is the base file

- **GIVEN** an authenticated free-tier user and a ready base pack
- **WHEN** they send `GET /api/models/on-device/file` with `X-Request-ID`
- **THEN** the Router responds HTTP 200 with the base weight bytes, logs the correlation id, and does not call the LLM container or publish Kafka

#### Scenario: Premium download

- **GIVEN** an authenticated premium user and a ready fine-tuned pack for that user
- **WHEN** they send `GET /api/models/on-device/file`
- **THEN** the Router responds HTTP 200 with that user's fine-tuned weight bytes

#### Scenario: Premium file is not substituted

- **GIVEN** an authenticated premium user and no ready fine-tuned pack for that user
- **WHEN** they send `GET /api/models/on-device/file`
- **THEN** the Router responds HTTP 404 and does not stream the base pack or another user's pack

#### Scenario: Free cannot download the fine-tuned pack

- **GIVEN** a ready fine-tuned pack and an authenticated free-tier user
- **WHEN** they send `GET /api/models/on-device/file`
- **THEN** the body is the base pack and not the fine-tuned pack

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service
information. The response SHALL include the service name `"api-gateway"`
and version. Model download routes SHALL NOT change this behavior and
SHALL continue to require a JWT.

#### Scenario: Public health

- **GIVEN** the API Router is running
- **WHEN** a client sends `GET /health`
- **THEN** the Router responds HTTP 200 without a JWT

#### Scenario: Model routes stay authenticated

- **GIVEN** the model routes are enabled
- **WHEN** a client sends `GET /health`
- **THEN** the health response is unchanged and still does not require a JWT
