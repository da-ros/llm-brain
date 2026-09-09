## Why

The microservices architecture requires a central API Router (Gateway) that:
- Validates JWT authentication from clients
- Generates and propagates correlation IDs (X-Request-ID)
- Routes requests to appropriate microservices (ETL, RAG, LLM)
- Handles async communication via Kafka (file uploads)
- Provides task status polling for async operations
- Implements rate limiting awareness

This is the **entry point** for all client requests in the microservices architecture.

### Context from Frame 1

Frame 1 established:
- **Microservices architecture** with API Router + Services
- **Kafka** for async communication (file uploads)
- **HTTP** for sync queries (chat, RAG)
- **Correlation ID** (X-Request-ID) for request tracing
- **Rate limiting** at the API Router (local MVP); AWS API Gateway is future/out of scope
- **MongoDB** (local container) for task status and file storage (GridFS)

### Context from Frame 2 & 3

- Frame 2 (ETL Service): Consumes from Kafka "file.uploaded", publishes to "task.response"
- Frame 3 (RAG Service): Provides semantic search and context injection via HTTP

## What Changes

### API Router Service
- FastAPI application on Port 8000
- JWT authentication middleware
- Correlation ID middleware (X-Request-ID)
- Kafka producer for file uploads
- Kafka consumer for task responses
- Task status endpoint (MongoDB polling)

### Routes
- `POST /api/upload` → Kafka (async) → 202 Accepted
- `POST /api/chat` → HTTP sync → 200 Response
- `GET /tasks/:correlation_id` → MongoDB polling
- `GET /health` → Health check

### Kafka Integration
- Producer: Publish to "file.uploaded" topic
- Consumer: Consume from "task.response" topic
- Update MongoDB task_status based on responses

### Retry Logic
- MAX_RETRIES configurable via .env
- DLQ (Dead Letter Queue) for permanent failures
- Task status tracking in MongoDB

## Output

```
output/
├── diagrams/
│   ├── api-router-architecture.drawio    ← Architecture diagram
│   ├── api-router-dataflow.drawio        ← Data flow diagram
│   └── README.md
└── documents/
    └── justificacion-ejemplo.md           ← Component explanations + SOLID
```

## Capabilities

### New Capabilities
- `api-router`: Central entry point for all client requests with JWT auth, correlation ID, and Kafka integration

### Modified Capabilities
- `platform-foundation`: Added API Router as separate service

## Execution Order

1. **Create FastAPI app** — Main app with middleware
2. **Implement JWT validation** — Auth dependency
3. **Add correlation ID middleware** — X-Request-ID generation/propagation
4. **Kafka producer** — Publish file uploads
5. **Kafka consumer** — Handle task responses
6. **Task status endpoint** — MongoDB polling
7. **Dockerfile + requirements** — Container setup
8. **Tests** — Unit and integration tests
