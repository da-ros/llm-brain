## Context

The API Router is the central entry point for all client requests in the microservices
architecture. It handles JWT authentication, correlation ID generation, routing to
microservices, and Kafka integration for async operations.

See proposal.md — Why. Depends on Frame 1 (microservices architecture, Kafka, MongoDB).

## Goals / Non-Goals

**Goals:**
- Central entry point for all client requests
- JWT authentication at router level
- Correlation ID (X-Request-ID) generation and propagation
- Kafka producer for file uploads
- Kafka consumer for task responses
- Task status polling via MongoDB
- Rate limiting at the API Router (local MVP); AWS API Gateway is future/out of scope

**Non-Goals:**
- No business logic — only routing and auth
- No direct database access for business data
- No service-to-service JWT (future enhancement)
- No WebSocket/Firebase (MVP uses polling)

## Architecture Decisions

### 1. Central Entry Point

**Decision**: All client requests go through the API Router.

```
Client → API Router → Services (ETL, RAG, LLM)
```

**Rationale**:
- Single point for auth, correlation ID, rate limiting
- Simplifies client logic (one endpoint to call)
- Easy to add cross-cutting concerns (logging, metrics)

### 2. JWT Authentication

**Decision**: Validate JWT at router level only.

```python
def verify_token(credentials):
    payload = jwt.decode(token, SECRET_KEY)
    return {"user_id": payload["sub"], "tier": payload["tier"]}
```

**Rationale**:
- Multi-tenant requires per-user authentication
- JWT is lightweight and stateless
- Services trust the router's auth (no service-to-service JWT yet)

### 3. Correlation ID Middleware

**Decision**: Generate/propagate X-Request-ID via middleware.

```python
@app.middleware("http")
async def add_correlation_id(request, call_next):
    correlation_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response
```

**Rationale**:
- Trace requests across services
- Link task status polling to original request
- Essential for debugging microservices

### 4. Kafka Producer (File Uploads)

**Decision**: Publish file upload messages to Kafka.

```
POST /api/upload → Kafka "file.uploaded" → 202 Accepted
```

**Rationale**:
- Async processing for heavy operations (OCR, parsing)
- Client gets immediate response (202)
- Decouple router from ETL service

### 5. Kafka Consumer (Task Responses)

**Decision**: Consume task responses and update MongoDB.

```
Kafka "task.response" → Update task_status in MongoDB
```

**Rationale**:
- Track async operation status
- Enable retry logic (DLQ)
- Provide status to polling clients

### 6. Task Status Polling

**Decision**: Client polls `GET /tasks/:correlation_id`.

```python
@app.get("/tasks/{correlation_id}")
async def get_task_status(correlation_id):
    task = await db.task_status.find_one({"_id": correlation_id})
    return task
```

**Rationale**:
- Simple implementation for MVP
- Works on web and mobile
- No WebSocket/Firebase dependency

### 7. MongoDB for Task Status

**Decision**: Store task status in MongoDB with TTL.

```javascript
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
- TTL indexes auto-clean old tasks
- Flexible schema for task metadata
- Single database for simplicity

### 8. Retry Logic with DLQ

**Decision**: Failed tasks retry up to MAX_RETRIES.

```
Error 5xx → Retry (retries < max_retries)
Error 3xx/4xx → Fail (no retry)
Max retries → dlq-max (permanent failure)
```

**Rationale**:
- Transient errors should retry
- Client errors should not retry
- DLQ allows manual inspection

### 9. Structured Logging with Correlation ID

**Decision**: All services use Python `logging` with correlation_id context.

```python
# Format
"%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s"

# Example output
2026-08-31T10:00:00 [550e8400-e29b-41d4-a716-446655440000] INFO api-gateway: POST /api/upload
2026-08-31T10:00:01 [550e8400-e29b-41d4-a716-446655440000] INFO etl-service: Processing file
```

**Rationale**:
- Trace requests across services for debugging
- Consistent format for log aggregation (ELK, CloudWatch)
- Correlation ID in every log line for easy filtering

**Implementation**:
- `CorrelationFilter` — adds correlation_id to all log records
- `log_with_correlation(id, level, message)` — helper function

## Data Flow

### Upload (Async)

```
1. POST /api/upload (file)
2. Router: validate JWT ✓
3. Router: generate correlationId
4. Router: save file to MongoDB GridFS
5. Router: save task_status {status: "in_progress"}
6. Router: publish to Kafka "file.uploaded"
7. Router: return 202 {correlation_id}

8. ETL Service: consume from Kafka
9. ETL Service: process file
10. ETL Service: publish to Kafka "task.response"

11. Router: consume response
12. Router: update task_status {status: "success"}

13. Client: poll GET /tasks/:id
14. Router: return {status: "success", triples_count: 15}
```

### Query (Sync)

```
1. POST /api/chat {message, use_rag: true}
2. Router: validate JWT ✓
3. Router: call RAG Service (HTTP)
4. Router: call LLM Service (HTTP)
5. Router: return 200 {response}
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Single point of failure | Router is stateless; scale horizontally |
| Kafka dependency | Use Docker Compose for local dev |
| MongoDB for task status | Acceptable for MVP; DynamoDB if needed |
| Polling wastes resources | Acceptable for ≤100 documents |

## Technology Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI (Python 3.13) |
| Auth | JWT + bcrypt (python-jose) |
| Message Queue | Apache Kafka (kafka-python) |
| Database | MongoDB (motor async driver) |
| File Storage | MongoDB GridFS |
| Container | Docker |

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **API Gateway / Facade** | API Router (local MVP); AWS API Gateway is future | Rate limiting, routing |
| **Facade** | API Router | Single entry point for clients |
| **Producer/Consumer** | Kafka integration | Async communication |
| **Middleware** | Correlation ID, JWT | Cross-cutting concerns |
| **Retry + DLQ** | Task status handling | Error recovery |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Router only handles routing and auth; no business logic |
| **O** | Add new route by adding new router — zero changes to main app |
| **L** | Any service can be called via same router interface |
| **I** | Router exposes minimal API (upload, chat, tasks, health) |
| **D** | Router depends on service abstractions (HTTP endpoints), not implementations |
