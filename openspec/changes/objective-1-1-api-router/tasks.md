## Tasks

### A. Gateway Foundation

- [x] A.1 Create FastAPI app in `services/api-router/main.py`
      — App initialization, middleware mounting, router includes
- [x] A.2 Implement correlation ID middleware
      — Generate X-Request-ID if not present, propagate in headers
- [x] A.3 Create configuration in `services/api-router/config.py`
      — JWT, Kafka, MongoDB, retry settings from .env
- [x] A.4 Create Dockerfile and requirements.txt
      — Container setup with health check

### B. JWT Authentication

- [x] B.1 Implement JWT verification dependency
      — Decode token, extract user_id and subscription_tier
- [x] B.2 Add auth to protected endpoints
      — upload, chat, tasks require valid JWT
- [x] B.3 Health endpoint remains public
      — No auth required for GET /health

### C. Kafka Integration

- [x] C.1 Implement Kafka producer for file uploads
      — Publish to "file.uploaded" topic with correlation_id
- [x] C.2 Implement Kafka consumer for task responses
      — Consume from "task.response" topic, update MongoDB
- [x] C.3 Add retry logic (MAX_RETRIES configurable)
      — Retry on 5xx errors, DLQ on max retries
- [x] C.4 Handle error responses (3xx/4xx = no retry)
      — Mark as "error" in task_status

### D. Task Status Endpoint

- [x] D.1 Implement GET /tasks/:correlation_id
      — Query MongoDB, return task status
- [x] D.2 Add user_id validation
      — User can only see their own tasks
- [x] D.3 Add TTL for task cleanup
      — MongoDB auto-delete after TASK_STATUS_TTL_DAYS

### E. Upload Router

- [x] E.1 Implement POST /api/upload
      — Validate file type/size, save to GridFS, publish to Kafka
- [x] E.2 Return 202 Accepted with correlation_id
      — Immediate response for async processing
- [x] E.3 Add premium tier validation
      — Only premium users can upload

### F. Chat Router

- [x] F.1 Implement POST /api/chat
      — Validate JWT, call RAG and LLM services
- [x] F.2 Add RAG context injection (premium only)
      — Call RAG Service for context, inject into prompt
- [x] F.3 Return 200 with response and correlation_id
      — Synchronous response

### G. Testing

- [x] G.1 Unit tests for correlation ID middleware
      — Test generation and propagation
- [x] G.2 Unit tests for JWT verification
      — Test valid/invalid tokens
- [x] G.3 Unit tests for task status endpoint
      — Test user isolation and status codes
- [x] G.4 Integration test: upload flow
      — Test full async flow with Kafka mock

### H. Documentation (output/documents/)

- [x] H.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns, SOLID principles
- [x] H.2 Create `output/diagrams/api-router-architecture.drawio`
      — Architecture diagram
- [x] H.3 Create `output/diagrams/api-router-dataflow.drawio`
      — Data flow diagram
