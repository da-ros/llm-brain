## Context

The ETL (Extract, Transform, Load) module is a **standalone microservice** that processes
user documents into structured knowledge triples. It runs as an independent FastAPI service
(Port 8001), consuming from Kafka topic "file.uploaded" and publishing results to "task.response".

See proposal.md — Why. Depends on Frame 1 (Microservices architecture, Kafka, API Router)
and calls the LLM Service (Frame 4, base Qwen3.5-4B) to extract triples.

## Goals / Non-Goals

**Goals:**
- Standalone service with own Dockerfile and FastAPI app
- Consume from Kafka topic "file.uploaded"
- Load any file type (text, PDF, images, video, HTML, EML) with **LangChain out-of-the-box loaders**
- Extract subject-predicate-object triples by **LLM reasoning** (Qwen3.5-4B via the LLM Service, port 8003)
- Store triples as JSONL on the filesystem for downstream RAG ingestion (Frame 3)
- Publish results to Kafka topic "task.response"
- Handle errors gracefully and report via Kafka
- Per-user isolation (triples tagged with `user_id`)

**Non-Goals:**
- No HTTP endpoint for file upload (API Router handles that)
- Real-time streaming ingestion (batch only in MVP)
- Live audio streaming transcription
- Hand-rolled parsers when a LangChain loader already exists
- Fine-tuning the extraction model (ETL uses the **base** Qwen3.5-4B; no adapter needed)

## Architecture Decisions

### 1. Standalone Microservice

**Decision**: ETL runs as independent FastAPI service on Port 8001.

```
Kafka (file.uploaded) → ETL Service (Port 8001) → Kafka (task.response)
```

**Rationale**:
- Independent scaling (LLM-based extraction is I/O + inference bound)
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

### 3. File Retrieval from MongoDB (local GridFS)

**Decision**: Read files from MongoDB GridFS (local container, not from Kafka message).

```
Kafka message: {correlation_id, file_id, user_id}
ETL: fetch original binary from MongoDB GridFS using file_id
ETL: load content with a LangChain loader
ETL: call LLM Service to extract triples
ETL: store triples JSONL in filesystem
```

**Rationale**:
- Kafka messages should be small (metadata only)
- GridFS (local MongoDB container) handles large binaries (text/PDF/image/video) efficiently
- File persists for retries
- Single source of truth for original binaries

### 4. LangChain Loader Selection

**Decision**: Use **`langchain_community.document_loaders`** out-of-the-box for every file
type; select the loader by MIME type. Do not hand-roll parsers unless no loader exists.

```python
# Loader selection (out-of-the-box LangChain loaders)
LOADERS = {
    "application/pdf": PyPDFLoader,          # or PDFPlumberLoader
    "text/plain":      TextLoader,
    "text/html":       UnstructuredHTMLLoader,
    "message/rfc822":  UnstructuredEmailLoader,
    "image/*":         UnstructuredImageLoader,  # OCR via Unstructured, not bespoke Tesseract
    "video/*":         <video loader>,
}
```

**Rationale**:
- Reuse battle-tested loaders instead of maintaining custom PDF/HTML/EML/OCR parsers
- OCR is handled by the LangChain `Unstructured*` loaders, not a bespoke Tesseract pipeline
- Open/Closed: add a new file type by registering another loader — existing code unchanged
- Strategy pattern: loader selection picks the right strategy at runtime

### 4b. LLM-First Triple Extraction

**Decision**: Extract triples by **LLM reasoning**, not rules/regex. The loaded content is
passed to the **base Qwen3.5-4B** model in the LLM Service (Frame 4, port 8003); the model
reasons over the content and emits JSON triples.

```
loader output (text/multimodal content)
    → POST LLM Service (8003) with base Qwen3.5-4B
    → model reasons over content
    → returns JSON triples [{subject, predicate, object, metadata}, ...]
```

**Rationale**:
- Handles unstructured, multimodal, multi-language content far better than regex
- Uses the **base** model — ETL needs no fine-tuning (the base model is enough)
- Dependency: Frame 4 (base Qwen3.5-4B inference) is built **before** Frame 2. Fine-tuning
  (also Frame 4) still consumes triples ETL accumulates, but only at **training runtime** —
  no circular build dependency. ETL itself only requires **base** inference.

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
    ├─ Fetch original binary from MongoDB GridFS (local)
    ├─ Detect MIME type (python-magic)
    ├─ Select LangChain loader (PyPDFLoader / TextLoader / Unstructured* / video loader)
    ├─ Load content (text/multimodal; OCR via Unstructured loaders)
    ├─ Call LLM Service (8003, base Qwen3.5-4B) → model reasons → emits JSON triples
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
| Kafka dependency | Use Docker Compose for local dev (LOCAL-ONLY MVP; managed MSK is future) |
| LLM Service dependency | ETL calls LLM Service (8003) for extraction; retry via Kafka; base model only |
| File not found in GridFS | Router validates file exists in local GridFS before publishing |
| Loader failures | Graceful degradation; report error via Kafka |
| Large files (>10MB) | Router rejects before Kafka; ETL has 10MB limit |
| Encoding issues | LangChain loaders handle decoding; fallback handled by the loader |

## Decisions Made

- Service: Standalone FastAPI on Port 8001
- Kafka topics: "file.uploaded" (input), "task.response" (output)
- File storage: MongoDB GridFS (local container; read binary via file_id)
- Loaders: LangChain `langchain_community.document_loaders` out-of-the-box (text/PDF/image/video/HTML/EML)
- Triple extraction: LLM-first via LLM Service (8003, base Qwen3.5-4B) — no rules/regex
- Triple format: JSON Lines with metadata
- Error reporting: Kafka "task.response" with status and error_message
- Per-user isolation: user_id in Kafka message and triple metadata

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Strategy** | LangChain loader selection | Each loader is a strategy; ETL selects at runtime by MIME type |
| **Factory Method** | distill() orchestrator | Selects the correct LangChain loader by MIME type |
| **Adapter** | LLM Service client | Wraps the LLM Service HTTP API for triple extraction |
| **Consumer/Producer** | Kafka integration | Async communication with API Router |
| **Facade** | ETL Service | Single entry point for document processing |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | ETL Service only loads content and orchestrates triple extraction; doesn't handle HTTP or auth |
| **O** | Add a new file type by registering another LangChain loader — zero changes to existing code |
| **L** | Any LangChain loader can replace another behind the selection layer |
| **I** | The loader selection layer exposes a minimal interface (select + load) |
| **D** | ETL depends on the loader abstraction and the LLM Service client, not concrete parsers |
