## Context

This is the first change in a greenfield repo (empty git repo, Python 3.13). It is
cross-cutting: it defines the microservices architecture and conventions that all remaining
thesis modules depend on. The project is a **multi-tenant platform** with two subscription
tiers (Free/Premium), using **Kafka** for async communication and **HTTP** for sync queries.

See proposal.md — Why. Budget is ~$0 and the deployment target is a multi-tenant MVP.
Architecture: API Router (FastAPI) + Microservices (ETL, RAG, LLM, Fine-Tune) + Kafka.

## Goals / Non-Goals

**Goals:**
- Microservices architecture with API Router as entry point
- Kafka for async communication (file uploads)
- HTTP sync for queries (chat, RAG)
- Correlation ID (X-Request-ID) for request tracing
- Rate limiting via AWS API Gateway (production)
- JWT authentication at API Router level
- MongoDB for task status and file storage (GridFS)
- Docker-based development and deployment
- CI that runs lint + tests on every push

**Non-Goals:**
- No monolithic backend — each service is independent
- No WebSocket/Firebase for MVP — polling for task status
- No service-to-service JWT (future enhancement)
- No production hardening (WAF, OAuth) — explicitly out of thesis scope

## Architecture Decisions

### 1. Microservices Architecture

**Decision**: Split the backend into independent services, each with its own Dockerfile.

| Service | Port | Responsibility |
|---------|------|----------------|
| API Router | 8000 | JWT validation, correlation ID, routing |
| ETL Service | 8001 | Document parsing, triple extraction |
| RAG Service | 8002 | MongoDB, Chroma, semantic search |
| LLM Service | 8003 | AWS Bedrock inference |
| Fine-Tune Service | 8004 | LoRA training (background worker) |

**Rationale**:
- Independent scaling per service
- Fault isolation (one service crash doesn't kill others)
- Easier to test and deploy individually
- Aligns with AWS ECS Fargate (one task per service)

### 2. Kafka for Async Communication

**Decision**: Use Kafka for file upload processing (heavy operations).

```
Cliente → API Router → Kafka (file.uploaded) → ETL Service
                          │
                          └── 202 Accepted + correlation ID
```

**Rationale**:
- File processing (OCR, parsing) takes seconds to minutes
- Don't block the client — return 202 immediately
- Retry failed tasks from DLQ (Dead Letter Queue)
- Decouple producer (Router) from consumer (ETL)

### 3. HTTP Sync for Queries

**Decision**: Use synchronous HTTP for chat and RAG queries.

```
Cliente → API Router → RAG Service → LLM Service → 200 Response
```

**Rationale**:
- Queries need immediate response (2-5 seconds acceptable)
- No benefit from async for fast operations
- Simpler implementation and debugging

### 4. Correlation ID (X-Request-ID)

**Decision**: Every request gets a UUID that travels through all services.

```
Header:  X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
Logs:    [550e8400-e29b-41d4-a716-446655440000] Processing file...
```

**Rationale**:
- Trace requests across services for debugging
- Link task status polling to original request
- Essential for microservices observability

### 5. Rate Limiting (AWS API Gateway)

**Decision**: Use AWS API Gateway rate limiting in production.

| Endpoint | Limit |
|----------|-------|
| POST /api/upload | 10 req/min |
| POST /api/chat | 30 req/min |
| GET /tasks/:id | 60 req/min |
| GET /health | 1000 req/min |

**Rationale**:
- Protects against abuse and bugs
- Free tier (1M requests/month)
- Configurable per endpoint

### 6. Task Status Polling

**Decision**: Client polls `GET /tasks/:correlation_id` for async results.

```
1. Upload → 202 {correlation_id}
2. Poll GET /tasks/:id every 2 seconds
3. Response: {status: "in_progress"} or {status: "success", result: {...}}
```

**Rationale**:
- Simple implementation, works on web and mobile
- No WebSocket/Firebase dependency
- Acceptable for MVP (≤100 documents)

### 7. MongoDB for Task Status + Files

**Decision**: MongoDB with GridFS for file storage and task tracking.

```javascript
// task_status collection
{
  _id: "correlation-id",
  status: "in_progress|success|error|dlq|dlq-max",
  service: "etl-service",
  retries: 0,
  max_retries: 3,
  expires_at: ISODate("...")  // TTL auto-delete
}
```

**Rationale**:
- GridFS handles binary files up to 5GB
- TTL indexes auto-clean old tasks
- Single database for simplicity (MVP)
- DynamoDB for production if needed later

### 8. Retry Logic with DLQ

**Decision**: Failed tasks retry up to MAX_RETRIES, then move to DLQ.

```
Error 5xx → Retry (retries < max_retries)
Error 3xx/4xx → Fail (no retry)
Max retries → dlq-max (permanent failure)
```

**Rationale**:
- Transient errors (503) should retry
- Client errors (422) should not retry
- DLQ allows manual inspection of permanent failures

### 9. JWT Authentication

**Decision**: JWT + bcrypt at API Router level only.

- Gateway validates JWT on initial request
- Reintents from DLQ skip JWT (file already authenticated)
- Future: service-to-service JWT for inter-service auth

**Rationale**:
- Multi-tenant requires per-user authentication
- JWT is lightweight and stateless
- Simpler than service mesh for MVP

### 10. Multi-Tenant with Subscription Tiers

**Decision**: Two tiers with different capabilities.

| Tier | LLM | Context | Files | Web Access |
|------|-----|---------|-------|------------|
| Free | llama.rn (on-device) | No | No | No |
| Premium | AWS Bedrock + RAG | Yes | Yes | Yes |

**Rationale**:
- Demonstrates tiered architecture
- Free tier proves local inference works
- Premium tier proves RAG + fine-tuning integration

## Data Flow

### Upload (Async via Kafka)

```
1. POST /api/upload (file)
2. API Router: validate JWT ✓
3. API Router: generate correlationId
4. API Router: save to MongoDB task_status {status: "in_progress"}
5. API Router: publish to Kafka "file.uploaded"
6. API Router: return 202 {correlation_id}

7. ETL Service: consume from Kafka
8. ETL Service: process file (parse, triples)
9. ETL Service: publish to Kafka "task.response" {status: "success"}
10. API Router: consume response, update MongoDB {status: "success"}

11. Client: poll GET /tasks/:id
12. API Router: return {status: "success", triples_count: 15}
```

### Query (Sync via HTTP)

```
1. POST /api/chat {message, use_rag: true}
2. API Router: validate JWT ✓
3. API Router: call RAG Service (HTTP) → context
4. API Router: call LLM Service (HTTP) → response
5. API Router: return 200 {response, context_used}
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Kafka adds complexity | Use Docker Compose for local dev; managed service in prod |
| Polling wastes resources | Acceptable for MVP (≤100 docs, 2s intervals) |
| MongoDB GridFS limits | 5GB per file;足够 for MVP |
| Service discovery | Use Docker DNS (container names) for local; ECS service discovery in prod |
| Distributed transactions | Accept eventual consistency; retry logic handles failures |

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| API Router | Python 3.13, FastAPI | Async-friendly, first-class testing |
| Microservices | Python 3.13, FastAPI | Independent deployment |
| Message Queue | Apache Kafka | Async communication, retry, DLQ |
| Document Store | MongoDB Atlas (GridFS) | Flexible schema, file storage |
| Vector Store | Chroma (local) / Pinecone (prod) | Semantic search |
| LLM Cloud | AWS Bedrock | Managed, free tier, fine-tuning |
| LLM Local | llama.rn (mobile only) | On-device inference |
| Web | React + Chart.js | Dashboard |
| Mobile | React Native | Cross-platform |
| Infra Local | Docker Compose | Fast dev iteration |
| Infra Prod | AWS ECS Fargate + API Gateway | Serverless, managed |
| CI/CD | GitHub Actions | Free tier |
| Encryption | Fernet (data), TLS (connection) | Simple, auditable |
| Trazabilidad | Correlation ID (X-Request-ID) | Request tracing |

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **API Gateway** | AWS API Gateway | Rate limiting, HTTPS, routing |
| **Message Broker** | Kafka | Async communication, retry, DLQ |
| **CQRS** | Sync queries vs async writes | Different patterns for different operations |
| **Retry + DLQ** | Task status handling | Transient error recovery |
| **Facade** | API Router | Single entry point for all clients |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Each service has ONE responsibility (ETL, RAG, LLM) |
| **O** | Add new service by creating new Dockerfile — zero changes to Router |
| **L** | Any service can be replaced (Chroma → Pinecone) without affecting others |
| **I** | Services expose minimal APIs (ETL: /process, RAG: /search) |
| **D** | API Router depends on service abstractions (HTTP endpoints), not implementations |

## Decisions Made

- Architecture: Microservices (not monolith)
- Communication: Kafka (async writes) + HTTP (sync reads)
- Correlation ID: X-Request-ID header + MongoDB task_status
- Rate Limiting: AWS API Gateway (production)
- Task Status: MongoDB with TTL auto-cleanup
- Retry: MAX_RETRIES=3, DLQ for permanent failures
- JWT: API Router only (no service-to-service JWT yet)
- Storage: MongoDB GridFS for files (DynamoDB future)
