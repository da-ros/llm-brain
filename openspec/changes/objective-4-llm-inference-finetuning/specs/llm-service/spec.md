# Spec: LLM Service

## ADDED Requirements

### Requirement: Multimodal inference over local Qwen3.5-4B

The LLM Service SHALL serve inference on port 8003 using **Qwen3.5-4B** (dense,
natively multimodal — text, image and video; 262K context; Apache 2.0; ~8 GB in
BF16, ~2.5–3 GB in Q4) as a **host process** ("cloud" = local process on port
8003, outside Docker Compose, reached from containers via
`host.docker.internal:8003`). The runtime SHALL be selected per machine with
`LLM_BACKEND` (see the backend-selection requirement below). It SHALL serve the
**base** full-precision model (**not** fine-tuned) for **web free** and for
**premium**. Web free is this same model with no RAG and no memory. Premium may
include RAG context supplied by the API Router.
It SHALL NOT call AWS Bedrock or any external
managed inference API, and it SHALL NOT depend on Llama models.

#### Scenario: Web free and premium text completion via the local backend

- **GIVEN** an authenticated web free or premium request
- **WHEN** the client sends `POST /generate` with a `prompt`, `user_id`, and `tier` of `free` or `premium`
- **THEN** the service runs the same base Qwen3.5-4B through the configured backend and responds HTTP 200 with `response` and `tokens_used`

#### Scenario: Multimodal chat with RAG context

- **GIVEN** an authenticated premium request that may include text, image and/or video input
- **WHEN** the client sends `POST /chat` with `messages`, optional RAG `context`, and `user_id`
- **THEN** the service performs multimodal inference (text, image, video) with Qwen3.5-4B and responds HTTP 200 with `response` and `tokens_used`

#### Scenario: Missing prompt is rejected

- **GIVEN** a `POST /generate` request without a `prompt`
- **WHEN** the service validates the body
- **THEN** it responds HTTP 400 without running inference

#### Scenario: Inference errors are surfaced

- **WHEN** the configured backend (Qwen local process or Ollama) is unavailable or the request times out
- **THEN** the service responds HTTP 500 (backend/model error) or HTTP 504 (timeout) and logs the error with the `X-Request-ID`

### Requirement: Backend selection via LLM_BACKEND

The service SHALL select its inference runtime from the `LLM_BACKEND` setting:
`qwen_local` (default — in-process Qwen3.5-4B via torch/Metal, Mac) or `ollama`
(HTTP to a local Ollama server, Linux/Windows). `QWEN_MOCK=true` SHALL win over
any backend: with the mock active the service SHALL NOT load weights nor open
network sockets, whatever `.env` configures. An unsupported `LLM_BACKEND` value
SHALL fail with `ValueError` when the provider is resolved.

#### Scenario: Mock wins over any backend

- **GIVEN** a machine whose `.env` sets `LLM_BACKEND=ollama` and `QWEN_MOCK=true`
- **WHEN** a request resolves the provider
- **THEN** the resolver returns the mock provider and no Ollama connection is attempted

#### Scenario: Ollama backend on Linux/Windows

- **GIVEN** a machine with `.env` `LLM_BACKEND=ollama`, `QWEN_MOCK=false`, and a running Ollama server
- **WHEN** a request resolves the provider
- **THEN** the resolver returns `OllamaProvider` pointing at `OLLAMA_URL` with model `OLLAMA_MODEL`

#### Scenario: Unknown backend is rejected

- **GIVEN** `.env` sets `LLM_BACKEND` to a value other than `qwen_local` or `ollama` and `QWEN_MOCK=false`
- **WHEN** a request resolves the provider
- **THEN** the service responds HTTP 500 and logs the `Unsupported LLM_BACKEND` error

### Requirement: The service serves web free on the base model

The LLM Service SHALL serve `tier=free` and `tier=premium` with the same base
Qwen3.5-4B weights. It SHALL NOT load a LoRA adapter for either tier. An
unknown tier SHALL be HTTP 400. Phone free SHALL NOT call this service: that
chat stays on the iPhone with the base Q4 pack (Frame 10).

#### Scenario: Web free uses the base model

- **GIVEN** a web free request with `tier=free`
- **WHEN** the API Router calls `POST /generate` or `POST /chat`
- **THEN** the service returns HTTP 200 from the base model, with no RAG context and no memory

#### Scenario: Phone free does not call this service

- **GIVEN** a free user on the iPhone
- **WHEN** they send a chat message
- **THEN** the phone answers with the base Q4 pack, and this service receives no request

#### Scenario: Unknown tier is rejected

- **GIVEN** a request whose `tier` is neither `free` nor `premium`
- **WHEN** the service resolves the provider
- **THEN** it responds HTTP 400 and does not run inference

### Requirement: Base model serves ETL triple extraction

The LLM Service SHALL expose its **base** Qwen3.5-4B so the ETL Service (Frame 2)
can reason over any document and extract triples. The base model SHALL NOT
require fine-tuning for triple extraction.

#### Scenario: ETL extracts triples via the base model

- **GIVEN** the ETL Service processing an uploaded document
- **WHEN** it calls the LLM Service with the document content
- **THEN** the base Qwen3.5-4B reasons over the content and returns triples (subject-predicate-object + metadata) in JSON

### Requirement: Health endpoint reports the real backend

The `GET /health` endpoint SHALL remain public and report the backend actually
in use: `backend` (`qwen_local` | `ollama`), `provider` (`mock` when
`QWEN_MOCK=true`, else `qwen-local` | `ollama`) and `model` (`qwen3.5-4b` for
`qwen_local`, `OLLAMA_MODEL` for `ollama`). It SHALL NOT expose secrets.

#### Scenario: Public health

- **GIVEN** the LLM Service is running
- **WHEN** a client sends `GET /health`
- **THEN** the service responds HTTP 200 with `service: "llm-service"`, the real `backend` and `provider`, and the `model` for that backend (e.g. `provider: "mock"` under CI defaults, `provider: "ollama"` with `LLM_BACKEND=ollama` and the mock off)

## Notes

### Port

8003

### Endpoints (technical reference)

#### POST /generate

Realiza una completion de texto con Qwen3.5-4B (backend local configurado).

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
- 400: Invalid request (missing prompt, or `tier` other than `free` or `premium`)
- 500: Inference error (backend unavailable / model error, p.ej. `Unsupported LLM_BACKEND`)
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

**Response 200** (backend real; ejemplo con mock activo — CI):
```json
{
  "status": "ok",
  "service": "llm-service",
  "backend": "qwen_local",
  "provider": "mock",
  "device": "auto",
  "model": "qwen3.5-4b",
  "version": "0.1.0"
}
```

Con `LLM_BACKEND=ollama` y `QWEN_MOCK=false`: `"backend": "ollama"`,
`"provider": "ollama"`, `"model": "qwen3.5:4b"`.

### Configuration

| Variable | Default | Descripción |
|----------|---------|-------------|
| `LLM_BACKEND` | `qwen_local` | Runtime: `qwen_local` (torch in-process) o `ollama` (server Ollama local) |
| `QWEN_MOCK` | `true` | Gana sobre cualquier backend; CI y tests nunca tocan un modelo real |
| `QWEN_MODEL_ID` | `qwen3.5-4b` | Modelo base servido (sin fine-tuning) |
| `QWEN_HF_MODEL_ID` | `Qwen/Qwen3.5-4B` | Repo de Hugging Face (descarga a `data/huggingface`) |
| `QWEN_DEVICE` | `auto` | `mps` (Mac) / `cuda` / `cpu` — solo backend `qwen_local` |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Server Ollama — solo backend `ollama` |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Tag del modelo en Ollama |
| `LLM_HOST` | `0.0.0.0` | Bind host |
| `LLM_PORT` | `8003` | Bind port |

### Dependencies

- Backend `qwen_local`: Qwen3.5-4B **base** BF16 de Hugging Face (~9.3 GB) + `requirements-gpu.txt` (torch, Mac)
- Backend `ollama`: server Ollama local + `ollama pull qwen3.5:4b` (~4 GB) — solo `httpx`, sin torch
- En ambos: `QWEN_MOCK=true` (default) no necesita nada

### Integration

- **Upstream**: API Router (`LLM_SERVICE_URL=http://host.docker.internal:8003`, idem en `docker-compose.yml`); ETL Service (Frame 2) llama al modelo base para extraer triples
- **Downstream** (`qwen_local`): pesos en `data/huggingface` / checkpoint local; (`ollama`): servidor Ollama en `OLLAMA_URL`

### Correlation ID

El servicio propaga el header `X-Request-ID` en logs estructurados:
```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars
2026-08-31T10:00:01 [abc-123] INFO llm-service: Qwen3.5-4B response: 150 tokens
```
