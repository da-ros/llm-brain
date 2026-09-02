## Tasks

### A. Pipeline Foundation

- [ ] A.1 Define `DocumentParser` protocol in `services/etl/base.py`
      — `supports(file_path) -> bool`, `parse(file_path) -> list[Triple]`
- [ ] A.2 Implement `Triple` dataclass in `services/etl/triples.py`
      — subject, predicate, object, metadata (source_file, page, section, timestamp, confidence)
- [ ] A.3 Implement `distill()` orchestrator in `services/etl/pipeline.py`
      — Routes file to correct parser based on MIME type, collects triples, writes JSONL output

### B. Parsers

- [ ] B.1 Implement PDF parser (`services/etl/parsers/pdf.py`)
      — PyPDF2 for text extraction, fallback to OCR for scanned pages
- [ ] B.2 Implement HTML parser (`services/etl/parsers/html.py`)
      — BeautifulSoup for text extraction, strip tags/scripts
- [ ] B.3 Implement EML parser (`services/etl/parsers/eml.py`)
      — email.parser for headers + body, handle attachments
- [ ] B.4 Implement Image/OCR parser (`services/etl/parsers/ocr.py`)
      — Tesseract via pytesseract, preprocess (grayscale, contrast)

### C. Triple Extraction

- [ ] C.1 Implement rule-based triple extraction (`services/etl/triples.py`)
      — Pattern matching: "X is Y", "X has Y", "X performs Y"
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

- [ ] E.1 Unit tests for each parser (mock file inputs)
- [ ] E.2 Unit tests for triple extraction patterns
- [ ] E.3 Integration test: upload PDF → triples generated
- [ ] E.4 Process >=100 sample documents and validate output quality
- [ ] E.5 Document pipeline configuration and usage in README

### F. Documentation (output/documents/)

- [ ] F.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns (Strategy, Factory, Facade), SOLID principles
- [ ] F.2 Document design patterns used: Strategy, Factory Method, Facade
- [ ] F.3 Document SOLID principles applied: SRP, OCP, LSP, ISP, DIP
