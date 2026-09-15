# ETL Service — One-Tap Memory Distillation

Standalone FastAPI service on **port 8001**. It does **not** accept file uploads over HTTP.
The API Router (`POST /api/upload`, port 8000) stores the binary in MongoDB GridFS and
publishes `file.uploaded`. This service consumes that topic, loads the file with
**LangChain out-of-the-box document loaders**, asks the **LLM Service (port 8003, base
Qwen3.5-4B)** to reason and emit JSON triples, writes JSONL, then publishes `task.response`.

## Pipeline

```
POST /api/upload (API Router, 202)
    → GridFS (original binary)
    → Kafka file.uploaded {correlation_id, file_id, user_id}
        → ETL :8001
            → fetch GridFS
            → python-magic MIME
            → select LangChain loader
            → load content
            → POST LLM Service /extract (base Qwen3.5-4B)
            → enrich metadata
            → data/triples/{user_id}/{correlation_id}.jsonl
            → Kafka task.response
```

Poll `GET /tasks/{correlation_id}` on the API Router for `triples_count`.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `API_PORT` | `8001` | ETL HTTP port (health only) |
| `MONGODB_URI` | `mongodb://localhost:27017` | Local MongoDB (GridFS) |
| `MONGODB_DB` | `llm_brain` | Database name |
| `KAFKA_ENABLED` | `true` | Set `false` in unit tests |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker |
| `KAFKA_TOPIC_FILE_UPLOADED` | `file.uploaded` | Input topic |
| `KAFKA_TOPIC_TASK_RESPONSE` | `task.response` | Output topic |
| `LLM_SERVICE_URL` | `http://localhost:8003` | Base Qwen3.5-4B inference |
| `LLM_TIMEOUT_SECONDS` | `35` | HTTP timeout to `/extract` |
| `MAX_FILE_SIZE` | `10485760` (10MB) | Defense-in-depth size cap |
| `TRIPLES_OUTPUT_DIR` | `./data/triples` | JSONL root (`{user_id}/{doc_id}.jsonl`) |

## Loaders (MIME → LangChain)

| MIME | Loader |
|------|--------|
| `application/pdf` | `PyPDFLoader` → `PDFPlumberLoader` → `UnstructuredPDFLoader` (OCR) |
| `text/plain` | `TextLoader` (encoding autodetect) |
| `text/html` | `UnstructuredHTMLLoader` |
| `message/rfc822` | `UnstructuredEmailLoader` |
| DOCX | `UnstructuredWordDocumentLoader` |
| `image/*` (raster) | `UnstructuredImageLoader` (OCR via Unstructured, not a custom Tesseract pipeline) |
| `video/*` | `VideoFileLoader` adapter over `UnstructuredFileLoader` |

There is **no** rule-based / regex triple extraction. The LLM emits JSON triples.

## Local usage

```bash
# Full stack
docker compose up --build etl-service llm-service api-router mongo kafka

# Health (independent of distillation)
curl http://localhost:8001/health

# Unit tests (Kafka disabled, LLM mocked)
pytest services/etl/test_etl.py
```

Programmatic (tests / notebooks):

```python
from pipeline import distill

triples = distill(
    "receta.pdf",
    user_id="user1",
    document_id="doc-1",
    mime_type="application/pdf",
)
```

## Errors

| Condition | HTTP (Router) | Kafka `task.response` |
|-----------|---------------|------------------------|
| Missing JWT | 401 | — |
| Free tier | 403 | — |
| Unsupported MIME | 422 | — |
| File > 10MB | 413 | — |
| Corrupt / loader failure | 202 then poll | `status=error`, `http_code=422` (no retry) |
| LLM Service 5xx / timeout | 202 then poll | `status=error`, `http_code=500` (Router retries) |
