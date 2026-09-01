## Purpose

The memory-distillation capability provides the data ingestion pipeline that converts
raw user documents (PDF, HTML, EML, images) into structured knowledge triples
(subject-predicate-object) with metadata, ready for RAG ingestion. It runs as a
FastAPI router within the backend, triggered by authenticated file uploads.

## ADDED Requirements

### Requirement: File upload endpoint

The system SHALL expose an authenticated `POST /api/upload` endpoint that accepts
file uploads and processes them into structured triples.

#### Scenario: Successful upload

- **WHEN** an authenticated user sends `POST /api/upload` with a valid file (PDF, HTML, EML, or image)
- **THEN** the system processes the file, extracts triples, and returns HTTP 201 with the number of triples generated

#### Scenario: Unauthenticated upload

- **WHEN** a client sends `POST /api/upload` without a valid JWT token
- **THEN** the system responds with HTTP 401

#### Scenario: File too large

- **WHEN** a client uploads a file larger than 10MB
- **THEN** the system responds with HTTP 413 and a descriptive error message

#### Scenario: Unsupported file type

- **WHEN** a client uploads a file with an unsupported MIME type (not PDF, HTML, EML, or image)
- **THEN** the system responds with HTTP 422 with a list of supported types

### Requirement: Document parsing

The system SHALL parse documents using type-specific parsers and extract text content.

#### Scenario: PDF with text

- **WHEN** a PDF file contains extractable text
- **THEN** the parser extracts text using PyPDF2 and returns it as a list of page strings

#### Scenario: PDF with scanned images

- **WHEN** a PDF file contains scanned images (no extractable text)
- **THEN** the parser falls back to OCR (Tesseract) and extracts text from each page image

#### Scenario: HTML document

- **WHEN** an HTML file is uploaded
- **THEN** the parser extracts text content using BeautifulSoup, stripping tags and scripts

#### Scenario: Email document

- **WHEN** an EML file is uploaded
- **THEN** the parser extracts headers (From, To, Subject, Date) and body text

#### Scenario: Image file

- **WHEN** an image file (PNG, JPG, etc.) is uploaded
- **THEN** the parser extracts text using Tesseract OCR with preprocessing (grayscale, contrast)

### Requirement: Triple extraction

The system SHALL extract subject-predicate-object triples from parsed text using
rule-based pattern matching.

#### Scenario: Simple sentence

- **WHEN** parsed text contains "Alice is a doctor"
- **THEN** the system extracts triple `{"subject": "Alice", "predicate": "is", "object": "a doctor"}`

#### Scenario: Possessive sentence

- **WHEN** parsed text contains "The patient has diabetes"
- **THEN** the system extracts triple `{"subject": "The patient", "predicate": "has", "object": "diabetes"}`

#### Scenario: Action sentence

- **WHEN** parsed text contains "The clinic performs surgeries"
- **THEN** the system extracts triple `{"subject": "The clinic", "predicate": "performs", "object": "surgeries"}`

### Requirement: Triple metadata enrichment

Each extracted triple SHALL include metadata with source information.

#### Scenario: Metadata fields

- **WHEN** a triple is extracted from a document
- **THEN** the triple metadata includes: `source_file`, `page` (if applicable), `section` (if applicable), `timestamp`, `confidence` (0.0-1.0)

### Requirement: Per-user data isolation

Triples SHALL be stored per-user, with no cross-user access.

#### Scenario: User-scoped output

- **WHEN** user A uploads a document
- **THEN** the triples are stored in `data/triples/{user_a_id}/{document_id}.jsonl`
- **AND** user B cannot access these triples through any endpoint

### Requirement: Error handling

The system SHALL handle errors gracefully and return descriptive error messages.

#### Scenario: Corrupt file

- **WHEN** a uploaded file is corrupt or unreadable
- **THEN** the system responds with HTTP 422 and an error message indicating the file is corrupt

#### Scenario: Encoding issues

- **WHEN** a file has encoding issues (non-UTF-8)
- **THEN** the parser attempts latin-1 fallback and continues processing

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain unchanged. The ETL pipeline does not affect
service liveness.
