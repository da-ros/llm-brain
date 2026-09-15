## Tasks

### A. Pipeline Foundation

- [x] A.1 Define LangChain loader selection layer in `services/etl/base.py`
      — map MIME type → `langchain_community.document_loaders` loader; expose `select(file_path)` + `load(file_path)`
- [x] A.2 Implement `Triple` dataclass in `services/etl/triples.py`
      — subject, predicate, object, metadata (source_file, page, section, timestamp, confidence)
- [x] A.3 Implement `distill()` orchestrator in `services/etl/pipeline.py`
      — Selects loader by MIME type, loads content, calls LLM Service for triples, writes JSONL output

### B. Loaders (LangChain out-of-the-box)

- [x] B.1 Wire PDF loading — `PyPDFLoader` / `PDFPlumberLoader` from `langchain_community.document_loaders`
- [x] B.2 Wire text loading — `TextLoader`
- [x] B.3 Wire HTML / EML / DOCX loading — `Unstructured*` loaders (e.g. `UnstructuredHTMLLoader`, `UnstructuredEmailLoader`)
- [x] B.4 Wire image + video loading — `UnstructuredImageLoader` (OCR via Unstructured) and a video loader; no bespoke Tesseract pipeline

### C. Triple Extraction (LLM-first)

- [x] C.1 Implement LLM Service client (`services/etl/llm_client.py`)
      — POST loaded content to LLM Service (8003, base Qwen3.5-4B); model reasons and returns JSON triples
- [x] C.2 Add metadata enrichment: source_file, page, section, timestamp, confidence
- [x] C.3 Implement JSONL writer with per-user isolation (`user_id` tag)

### D. FastAPI Integration

- [x] D.1 Create upload router (`apps/api/routers/upload.py`)
      — `POST /api/upload` with JWT auth dependency
- [x] D.2 Wire distill pipeline to upload endpoint
      — Accept file, validate type/size, process, return triples count
- [x] D.3 Add file type validation via `python-magic` (MIME detection, not extension)
- [x] D.4 Add size limit (max 10MB) and error handling
      — Corrupt files, unsupported formats, encoding issues → HTTP 422

### E. Testing & Validation

- [x] E.1 Unit tests for each LangChain loader wrapper (mock file inputs)
- [x] E.2 Unit tests for LLM triple extraction (mock LLM Service responses)
- [x] E.3 Integration test: upload PDF → LLM extracts triples → JSONL generated
- [x] E.4 Process >=100 sample documents and validate output quality
- [x] E.5 Document pipeline configuration and usage in README

### F. Documentation (output/)

- [x] F.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns (Strategy, Factory, Adapter, Facade), SOLID principles
- [x] F.2 Document design patterns used: Strategy, Factory Method, Adapter, Facade
- [x] F.3 Document SOLID principles applied: SRP, OCP, LSP, ISP, DIP
- [x] F.4 Create `output/diagrams/etl-architecture.drawio`
      — Architecture base: existing Frame 1 services in blue, ETL Service (8001) in green; Kafka, GridFS, LLM Service (8003)
- [x] F.5 Create `output/diagrams/etl-dataflow.drawio`
      — Data flow: `file.uploaded` → GridFS fetch → LangChain loader → LLM triples → JSONL → `task.response`, including error paths
- [x] F.6 Create `output/diagrams/README.md`
