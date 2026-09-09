# Spec: LLM Service

## ADDED Requirements

### Requirement: Multimodal inference over local Qwen3.5-4B

The LLM Service SHALL serve inference on port 8003 using **Qwen3.5-4B** (dense,
natively multimodal — text, image and video; 262K context; Apache 2.0; ~8 GB in
BF16, ~2.5–3 GB in Q4) running in a **local Docker container** ("cloud" = local
container). It SHALL serve the **base** full-precision model (**not** fine-tuned) for
**premium** users (with RAG). It SHALL NOT call AWS Bedrock or any external
managed inference API, and it SHALL NOT depend on Llama models.

#### Scenario: Premium text completion via local container

- **GIVEN** an authenticated premium request
- **WHEN** the client sends `POST /generate` with a `prompt` and `user_id`
- **THEN** the service runs Qwen3.5-4B in the local container and responds HTTP 200 with `response` and `tokens_used`

#### Scenario: Multimodal chat with RAG context

- **GIVEN** an authenticated premium request that may include text, image and/or video input
- **WHEN** the client sends `POST /chat` with `messages`, optional RAG `context`, and `user_id`
- **THEN** the service performs multimodal inference (text, image, video) with Qwen3.5-4B and responds HTTP 200 with `response` and `tokens_used`

#### Scenario: Missing prompt is rejected

- **GIVEN** a `POST /generate` request without a `prompt`
- **WHEN** the service validates the body
- **THEN** it responds HTTP 400 without running inference

#### Scenario: Inference errors are surfaced

- **WHEN** the local Qwen3.5-4B container is unavailable or the request times out
- **THEN** the service responds HTTP 500 (container/model error) or HTTP 504 (timeout) and logs the error with the `X-Request-ID`

### Requirement: Free tier is not served by the container

The LLM Service SHALL only serve **premium** inference. The **free** tier SHALL
be served by Qwen3.5-4B **base** quantized (Q4) on-device in React Native on
iPhone via **Neural Engine / Metal** (Frame 10), not by this container. Free
users SHALL NOT access this cloud service.

#### Scenario: Free tier routed on-device

- **GIVEN** a free-tier user
- **WHEN** they issue a chat request
- **THEN** the request is handled on-device by the **base** quantized Qwen3.5-4B in React Native (Neural Engine / Metal), and this service does not process it

### Requirement: Base model serves ETL triple extraction

The LLM Service SHALL expose its **base** Qwen3.5-4B so the ETL Service (Frame 2)
can reason over any document and extract triples. The base model SHALL NOT
require fine-tuning for triple extraction.

#### Scenario: ETL extracts triples via the base model

- **GIVEN** the ETL Service processing an uploaded document
- **WHEN** it calls the LLM Service with the document content
- **THEN** the base Qwen3.5-4B reasons over the content and returns triples (subject-predicate-object + metadata) in JSON

### Requirement: Health endpoint reports the local Qwen model

The `GET /health` endpoint SHALL remain public and report the served model as
the local Qwen3.5-4B container.

#### Scenario: Public health

- **GIVEN** the LLM Service is running
- **WHEN** a client sends `GET /health`
- **THEN** the service responds HTTP 200 with `service: "llm-service"`, `provider` indicating the local Qwen3.5-4B container, and `model: "qwen3.5-4b"`

## Notes

### Port

8003

### Endpoints (technical reference)

#### POST /generate

Realiza una completion de texto con Qwen3.5-4B (contenedor local).

**Request**:
```json
{
  "prompt": "¿Cuándo debo tomar la medicina?",
  "user_id": "user-123"
}
```

**Response 200**:
```json
{
  "response": "Basado en tu receta médica...",
  "tokens_used": 150
}
```

**Errors**:
- 400: Invalid request (missing prompt)
- 500: Inference error (local Qwen3.5-4B container unavailable / model error)
- 504: Inference timeout

#### POST /chat

Realiza un chat multimodal (texto, imagen, video) con contexto RAG opcional.

**Request**:
```json
{
  "messages": [
    {"role": "user", "content": "¿Qué debo comprar esta semana?"}
  ],
  "context": "Receta: Ibuprofeno 400mg, 3 veces al día",
  "user_id": "user-123"
}
```

**Response 200**:
```json
{
  "response": "Basado en tu receta, deberías comprar Ibuprofeno...",
  "tokens_used": 200
}
```

#### GET /health

**Response 200**:
```json
{
  "status": "ok",
  "service": "llm-service",
  "provider": "qwen-local-container",
  "model": "qwen3.5-4b",
  "version": "0.1.0"
}
```

### Configuration

| Variable | Default | Descripción |
|----------|---------|-------------|
| `QWEN_MODEL_ID` | `qwen3.5-4b` | Modelo base servido en el contenedor local (sin fine-tuning) |
| `LLM_HOST` | `0.0.0.0` | Bind host |
| `LLM_PORT` | `8003` | Bind port |

### Dependencies

- Qwen3.5-4B **base** (contenedor Docker local; "cloud" = local container; not fine-tuned)

### Integration

- **Upstream**: API Router (`services/api-router/routers/chat.py`) llama a `http://llm-service:8003/generate`; ETL Service (Frame 2) llama al modelo base para extraer triples
- **Downstream**: contenedor local Qwen3.5-4B

### Correlation ID

El servicio propaga el header `X-Request-ID` en logs estructurados:
```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars
2026-08-31T10:00:01 [abc-123] INFO llm-service: Qwen3.5-4B response: 150 tokens
```
