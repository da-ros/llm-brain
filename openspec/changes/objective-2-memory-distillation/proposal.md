## Why

Users need to load personal documents (medical recipes, invoices, photos, emails)
into the platform and have them automatically processed into structured knowledge
triples (subject-predicate-object) that the LLM can reason over via RAG.

This is **Objetivo Específico 2** of the thesis: the "One-Tap Memory Distillation"
pipeline that converts unstructured documents into structured JSON triples.

### Context from Frame 1

Frame 1 established:
- **FastAPI backend** with JWT auth, config layer, and LLM provider abstraction
- **MongoDB** for document storage, **Chroma** for vector embeddings
- **Docker Compose** for local development
- **Per-user data isolation** via `user_id` scoping

The ETL pipeline integrates with this foundation:
- Triggers on `POST /api/upload` (new FastAPI router)
- Stores original documents in MongoDB (per-user scoped)
- Outputs JSON triples to `data/triples/{user_id}/`
- Feeds into Frame 3 (RAG) for vector embeddings

## What Changes

### ETL Pipeline
- Define `DocumentParser` protocol in `services/etl/base.py`
- Implement `Triple` dataclass: subject, predicate, object, metadata
- Implement `distill()` orchestrator in `services/etl/pipeline.py`

### Parsers
- PDF parser (`services/etl/parsers/pdf.py`) — PyPDF2 + OCR fallback
- HTML parser (`services/etl/parsers/html.py`) — BeautifulSoup
- EML parser (`services/etl/parsers/eml.py`) — email.parser
- Image/OCR parser (`services/etl/parsers/ocr.py`) — Tesseract via pytesseract

### Triple Extraction
- Rule-based extraction: "X is Y", "X has Y", "X performs Y"
- Metadata enrichment: source_file, page, section, timestamp, confidence
- JSONL writer with per-user isolation (`user_id` tag)

### FastAPI Integration
- New router: `apps/api/routers/upload.py`
- File upload endpoint: `POST /api/upload`
- File type validation and size limits (max 10MB)
- Error handling: corrupt files, unsupported formats, encoding issues

### Tests
- Unit tests for each parser (mock file inputs)
- Unit tests for triple extraction patterns
- Integration test: upload PDF → triples generated
- Process >=100 sample documents and validate output quality

## Output

```
output/
├── diagrams/
│   ├── etl-architecture.drawio    ← Architecture base diagram
│   ├── etl-dataflow.drawio        ← Data flow diagram
│   └── README.md
└── documents/
    └── justificacion-ejemplo.md   ← Component explanations
```

## Capabilities

### New Capabilities
- `memory-distillation`: ETL pipeline that converts documents (PDF, HTML, EML, images)
  into structured JSON triples with metadata, ready for RAG ingestion

### Modified Capabilities
- `platform-foundation`: Added `POST /api/upload` router for file ingestion

## Impact

- New code: `services/etl/` (parsers, pipeline, triples), `apps/api/routers/upload.py`
- New dependencies: PyPDF2, BeautifulSoup, pytesseract, python-magic
- Integrates with: MongoDB (document storage), Frame 3 (RAG ingestion)
- No changes to existing auth, config, or LLM provider layers

## Execution Order

1. **Define contracts** — `DocumentParser` protocol, `Triple` dataclass
2. **Implement parsers** — PDF, HTML, EML, OCR (one at a time, test each)
3. **Implement orchestrator** — `distill()` function that routes files to parsers
4. **Wire to FastAPI** — Upload endpoint with validation
5. **Test everything** — Unit + integration tests
6. **Validate** — Process >=100 sample documents
