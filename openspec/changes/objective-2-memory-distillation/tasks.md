## Tasks

### A. Pipeline Foundation

- [ ] A.1 Define `DocumentParser` protocol in `services/etl/base.py`
      — parse(file_path) -> list[Triple], supports() -> bool
- [ ] A.2 Implement `Triple` dataclass: subject, predicate, object, metadata
- [ ] A.3 Implement `distill()` orchestrator in `services/etl/pipeline.py`
      — Routes file to correct parser, collects triples, writes JSONL output

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

- [ ] C.1 Implement simple rule-based triple extraction (`services/etl/triples.py`)
      — Pattern matching: "X is Y", "X has Y", "X performs Y"
- [ ] C.2 Add metadata enrichment: source_file, page, section, timestamp, confidence
- [ ] C.3 Implement JSONL writer with per-user isolation (user_id tag)

### D. Integration

- [ ] D.1 Wire distill pipeline to file upload endpoint (`POST /api/upload`)
- [ ] D.2 Add file type validation and size limits (max 10MB)
- [ ] D.3 Add error handling: corrupt files, unsupported formats, encoding issues

### E. Testing & Validation

- [ ] E.1 Unit tests for each parser (mock file inputs)
- [ ] E.2 Unit tests for triple extraction patterns
- [ ] E.3 Integration test: upload PDF -> triples generated
- [ ] E.4 Process >=100 sample documents and validate output quality
- [ ] E.5 Document pipeline configuration and usage in README
