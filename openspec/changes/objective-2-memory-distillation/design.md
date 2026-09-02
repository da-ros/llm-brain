## Context

The ETL (Extract, Transform, Load) module is a **standalone microservice** that processes
user documents into structured knowledge triples. It runs as an independent FastAPI service
(Port 8001), consuming from Kafka topic "file.uploaded" and publishing results to "task.response".

See proposal.md — Why. Depends on Frame 1 (Microservices architecture, Kafka, API Router).

## Goals / Non-Goals

**Goals:**
- Standalone service with own Dockerfile and FastAPI app
- Consume from Kafka topic "file.uploaded"
- Parse PDF, HTML, EML, and image (OCR) documents
- Extract subject-predicate-object triples with metadata
- Store triples as JSONL for downstream RAG ingestion (Frame 3)
- Publish results to Kafka topic "task.response"
- Handle errors gracefully and report via Kafka
- Per-user isolation (triples tagged with `user_id`)

**Non-Goals:**
- No HTTP endpoint for file upload (Gateway handles that)
- Real-time streaming ingestion (batch only in MVP)
- Audio/video transcription
- Multi-language OCR beyond Spanish + English

## Architecture Decisions

### 1. Standalone Microservice

**Decision**: ETL runs as independent FastAPI service on Port 8001.

```
Kafka (file.uploaded) → ETL Service (Port 8001) → Kafka (task.response)
```

**Rationale**:
- Independent scaling (OCR is CPU-intensive)
- Fault isolation (ETL crash doesn't affect Router)
- Own Dockerfile for deployment
- Can run multiple instances for parallel processing

### 2. Kafka Consumer/Producer

**Decision**: Consume from "file.uploaded", publish to "task.response".

```python
# Consumer
consumer = KafkaConsumer('file.uploaded', ...)
for message in consumer:
    process_file(message.value)

# Producer
producer = KafkaProducer(...)
producer.send('task.response', value=result)
```

**Rationale**:
- Decoupled from API Router
- Built-in retry via Kafka
- DLQ for failed messages
- Natural backpressure handling

### 3. File Retrieval from MongoDB

**Decision**: Read files from MongoDB GridFS (not from Kafka message).

```
Kafka message: {correlation_id, file_id, user_id}
ETL: fetch file from MongoDB GridFS using file_id
ETL: process file
ETL: store triples in filesystem
```

**Rationale**:
- Kafka messages should be small (metadata only)
- GridFS handles large files efficiently
- File persists for retries
- Single source of truth for files

### 4. DocumentParser Protocol

**Decision**: Define `DocumentParser` as a Python Protocol.

```python
class DocumentParser(Protocol):
    def supports(self, file_path: str) -> bool: ...
    def parse(self, file_path: str) -> list[Triple]: ...
```

**Rationale**:
- Open/Closed: add new parser without modifying existing code
- Strategy pattern: each parser is a strategy
- Pythonic (structural subtyping)

### 5. Triple Format: JSON Lines

**Decision**: Output triples as JSON Lines (one triple per line).

```
{"subject": "Patient", "predicate": "has", "object": "diabetes", "metadata": {...}}
{"subject": "Patient", "predicate": "takes", "object": "metformin", "metadata": {...}}
```

**Rationale**:
- Streaming-friendly (append-only)
- Easy to incrementally ingest into vector store (Frame 3)
- Human-readable for debugging

### 6. Error Reporting via Kafka

**Decision**: Report success/failure via Kafka "task.response" topic.

```python
# Success
producer.send('task.response', value={
    'correlation_id': 'abc-123',
    'status': 'success',
    'triples_count': 15
})

# Error
producer.send('task.response', value={
    'correlation_id': 'abc-123',
    'status': 'error',
    'http_code': 500,
    'error_message': 'OCR failed'
})
```

**Rationale**:
- Gateway updates MongoDB task_status based on response
- Retry logic handled by Gateway
- Consistent error reporting format

## Data Flow

```
Kafka (file.uploaded)
    │
    ▼
ETL Service (Port 8001)
    │
    ├─ Fetch file from MongoDB GridFS
    ├─ Detect MIME type (python-magic)
    ├─ Route to correct parser (PDF/HTML/EML/OCR)
    ├─ Extract text
    ├─ Extract triples (rule-based)
    ├─ Enrich metadata (source, page, timestamp)
    ├─ Write JSONL to filesystem
    │
    ▼
Kafka (task.response)
    │
    ├─ Success: {status: "success", triples_count: 15}
    └─ Error: {status: "error", http_code: 500, error_message: "..."}
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Kafka dependency | Use Docker Compose for local dev; managed MSK in prod |
| File not found in GridFS | Gateway validates file exists before publishing |
| Parser failures | Graceful degradation; report error via Kafka |
| Large files (>10MB) | Gateway rejects before Kafka; ETL has 10MB limit |
| Encoding issues | Force UTF-8, fallback to latin-1 |

## Decisions Made

- Service: Standalone FastAPI on Port 8001
- Kafka topics: "file.uploaded" (input), "task.response" (output)
- File storage: MongoDB GridFS (read via file_id from Kafka message)
- Parser interface: Python Protocol (DocumentParser)
- Triple format: JSON Lines with metadata
- Error reporting: Kafka "task.response" with status and error_message
- Per-user isolation: user_id in Kafka message and triple metadata

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Strategy** | DocumentParser protocol + concrete parsers | Each parser is a strategy; ETL selects at runtime |
| **Factory Method** | distill() orchestrator | Routes file to correct parser by MIME type |
| **Consumer/Producer** | Kafka integration | Async communication with Gateway |
| **Facade** | ETL Service | Single entry point for document processing |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | ETL Service only processes documents; doesn't handle HTTP or auth |
| **O** | Add new parser (e.g., Word) by creating new class — zero changes to ETL |
| **L** | Any DocumentParser implementation can replace another |
| **I** | DocumentParser protocol has only 2 methods: supports, parse |
| **D** | ETL depends on DocumentParser abstraction, not concrete parsers |
