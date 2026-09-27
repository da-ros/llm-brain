## Why

Users need to load personal documents (medical recipes, invoices, photos, videos, emails)
into the platform and have them automatically processed into structured knowledge
triples (subject-predicate-object) that the LLM can reason over via RAG.

This is **Objetivo Específico 2** of the thesis: the "One-Tap Memory Distillation"
pipeline that converts unstructured documents (text, PDF, images, video) into
structured JSON triples using **LangChain document loaders** and **LLM-based reasoning**.

### Context from Frame 1

Frame 1 established:
- **FastAPI backend** with JWT auth, config layer, and LLM Service (Qwen3.5-4B, local container)
- **MongoDB (local container, GridFS)** for original binaries, **Chroma** for vector embeddings
- **Docker Compose** for local development (LOCAL-ONLY MVP; AWS is future/out of scope)
- **Per-user data isolation** via `user_id` scoping

The ETL pipeline integrates with this foundation:
- Triggers on `POST /api/upload` (async via Kafka `file.uploaded`)
- Reads original documents from MongoDB GridFS (local, per-user scoped)
- Calls the **LLM Service (Frame 4)** with the **base Qwen3.5-4B** model to extract triples
- Outputs JSON triples (JSONL) to `data/triples/{user_id}/` on the filesystem
- Feeds into Frame 3 (RAG) for vector embeddings

## What Changes

### ETL Pipeline
- Define `DocumentLoader` selection layer in `services/etl/base.py` (wraps LangChain loaders)
- Implement `Triple` dataclass: subject, predicate, object, metadata
- Implement `distill()` orchestrator in `services/etl/pipeline.py`

### Loaders (LangChain out-of-the-box)
- All parsing uses **`langchain_community.document_loaders`** out-of-the-box — no hand-rolled parsers unless no loader exists
- PDF → `PyPDFLoader` / `PDFPlumberLoader`
- Text → `TextLoader`
- HTML / EML / DOCX / images (OCR) → `Unstructured*` loaders (e.g. `UnstructuredHTMLLoader`, `UnstructuredEmailLoader`, `UnstructuredImageLoader`)
- Images / video → image/video loaders (OCR handled by the LangChain Unstructured loaders, not a bespoke Tesseract pipeline)

### Triple Extraction (LLM-first)
- Any file → LangChain loader loads content → content passed to **Qwen3.5-4B (LLM Service, port 8003)**
- The model **reasons** over the loaded content and **then emits JSON triples** (subject-predicate-object + metadata)
- No rule-based / regex / heuristic extraction — extraction is LLM-first reasoning
- Metadata enrichment: source_file, page, section, timestamp, confidence
- JSONL writer with per-user isolation (`user_id` tag)

### FastAPI Integration
- New router: `services/api-router/routers/upload.py`
- File upload endpoint: `POST /api/upload`
- File type validation and size limits (max 10MB)
- Error handling: corrupt files, unsupported formats, encoding issues

### Tests
- Unit tests for each LangChain loader wrapper (mock file inputs)
- Unit tests for LLM triple extraction (mock LLM Service responses)
- Integration test: upload PDF → LLM extracts triples → JSONL generated
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
- `memory-distillation`: ETL pipeline that loads documents (text, PDF, images, video, HTML, EML)
  with LangChain loaders and uses LLM reasoning (Qwen3.5-4B) to convert them into structured
  JSON triples with metadata, ready for RAG ingestion

### Modified Capabilities
- `platform-foundation`: Added `POST /api/upload` router for file ingestion

## Impact

- New code: `services/etl/` (loader selection, pipeline, triples, LLM client)
- New dependencies: `langchain-community` document loaders (`unstructured`, `pypdf`/`pdfplumber`), python-magic; an HTTP client to the LLM Service (8003)
- **New cross-frame dependency:** Frame 4 (LLM Service, **base** Qwen3.5-4B) is built
  **before** Frame 2. ETL calls that service to extract triples. The Fine-Tune Service
  (also Frame 4) is implemented with inference, but **training** consumes Frame 2 triples
  at **runtime** only — no circular build dependency.
- Original binaries (text/PDF/image/video) stored in **MongoDB GridFS (local container)**;
  extracted text chunks are later stored in Chroma by the RAG service; triples JSONL on filesystem
- Integrates with: MongoDB GridFS (binaries), LLM Service (triple extraction), Frame 3 (RAG ingestion)
- No changes to existing auth, config, or LLM Service layers
- Deployment: LOCAL-ONLY MVP (Docker Compose); AWS is future/out of scope

## Execution Order

1. **Define contracts** — LangChain loader selection layer, `Triple` dataclass
2. **Wire loaders** — Configure `langchain_community.document_loaders` per file type (text, PDF, images, video, HTML, EML)
3. **Implement orchestrator** — `distill()` loads content and calls the LLM Service (base Qwen3.5-4B) to emit triples
4. **Wire to FastAPI** — Upload endpoint with validation
5. **Test everything** — Unit + integration tests
6. **Validate** — Process >=100 sample documents
