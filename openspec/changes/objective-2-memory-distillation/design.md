## Context

The memory distillation module is the data ingestion pipeline that converts raw
user documents into structured knowledge triples. It runs as a background service
within the FastAPI backend, triggered by file uploads.

## Goals / Non-Goals

**Goals:**
- Parse PDF, HTML, EML, and image (OCR) documents
- Extract subject-predicate-object triples with metadata
- Store triples as JSON for downstream RAG ingestion
- Process >=100 documents in validation
- Handle errors gracefully (corrupt files, unsupported formats)

**Non-Goals:**
- Real-time streaming ingestion
- Audio/video transcription
- Multi-language OCR beyond Spanish + English

## Architecture Decisions

### 1. Pipeline Architecture: Modular Parsers

**Decision**: One parser per document type, orchestrated by a central `distill()` function.

**Rationale**:
- Each parser is independently testable
- New formats added by implementing one interface
- Follows Open/Closed principle

### 2. OCR: Tesseract via pytesseract

**Decision**: Use Tesseract OCR for image text extraction.

**Rationale**:
- Open source, no API costs
- Good Spanish + English support
- Runs locally (no data leaves the device/server)

### 3. Triple Format: JSON Lines

**Decision**: Output triples as JSON Lines (one triple per line).

**Rationale**:
- Streaming-friendly (append-only)
- Easy to incrementally ingest into vector store
- Human-readable for debugging

### 4. Processing: Synchronous per-file, async queue (future)

**Decision**: Synchronous processing in MVP, async queue in future.

**Rationale**:
- MVP scope is <=100 documents (synchronous is fine)
- Async adds complexity (Celery/Redis) not needed yet
- Easy to upgrade later

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Tesseract accuracy on low-quality images | Pre-process: grayscale, contrast enhancement |
| PDF with scanned images (not text) | Detect via PyPDF2 text extraction, fallback to OCR |
| Large files (>10MB) | Reject with clear error, document size limits |
| Encoding issues in EML/HTML | Force UTF-8, fallback to latin-1 |

## Decisions Made

- Triple format: `{"subject": "...", "predicate": "...", "object": "...", "metadata": {...}}`
- Metadata includes: source_file, page, section, timestamp, confidence
- Output stored in `data/triples/{document_id}.jsonl`
- Per-user isolation: triples tagged with user_id
