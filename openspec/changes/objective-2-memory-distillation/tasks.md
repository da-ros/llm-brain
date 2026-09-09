## Tasks

### A. Pipeline Foundation

- [ ] A.1 Define LangChain loader selection layer in `services/etl/base.py`
      — map MIME type → `langchain_community.document_loaders` loader; expose `select(file_path)` + `load(file_path)`
- [ ] A.2 Implement `Triple` dataclass in `services/etl/triples.py`
      — subject, predicate, object, metadata (source_file, page, section, timestamp, confidence)
- [ ] A.3 Implement `distill()` orchestrator in `services/etl/pipeline.py`
      — Selects loader by MIME type, loads content, calls LLM Service for triples, writes JSONL output

### B. Loaders (LangChain out-of-the-box)

- [ ] B.1 Wire PDF loading — `PyPDFLoader` / `PDFPlumberLoader` from `langchain_community.document_loaders`
- [ ] B.2 Wire text loading — `TextLoader`
- [ ] B.3 Wire HTML / EML / DOCX loading — `Unstructured*` loaders (e.g. `UnstructuredHTMLLoader`, `UnstructuredEmailLoader`)
- [ ] B.4 Wire image + video loading — `UnstructuredImageLoader` (OCR via Unstructured) and a video loader; no bespoke Tesseract pipeline

### C. Triple Extraction (LLM-first)

- [ ] C.1 Implement LLM Service client (`services/etl/llm_client.py`)
      — POST loaded content to LLM Service (8003, base Qwen3.5-4B); model reasons and returns JSON triples
- [ ] C.2 Add metadata enrichment: source_file, page, section, timestamp, confidence
- [ ] C.3 Implement JSONL writer with per-user isolation (`user_id` tag)

### D. FastAPI Integration

- [ ] D.1 Create upload router (`apps/api/routers/upload.py`)
      — `POST /api/upload` with JWT auth dependency
- [ ] D.2 Wire distill pipeline to upload endpoint
      — Accept file, validate type/size, process, return triples count
- [ ] D.3 Add file type validation via `python-magic` (MIME detection, not extension)
- [ ] D.4 Add size limit (max 10MB) and error handling
      — Corrupt files, unsupported formats, encoding issues → HTTP 422

### E. Testing & Validation

- [ ] E.1 Unit tests for each LangChain loader wrapper (mock file inputs)
- [ ] E.2 Unit tests for LLM triple extraction (mock LLM Service responses)
- [ ] E.3 Integration test: upload PDF → LLM extracts triples → JSONL generated
- [ ] E.4 Process >=100 sample documents and validate output quality
- [ ] E.5 Document pipeline configuration and usage in README

### F. Documentation (output/documents/)

- [ ] F.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns (Strategy, Factory, Adapter, Facade), SOLID principles
- [ ] F.2 Document design patterns used: Strategy, Factory Method, Adapter, Facade
- [ ] F.3 Document SOLID principles applied: SRP, OCP, LSP, ISP, DIP
