## Purpose

The memory-distillation capability provides the data ingestion pipeline that converts
raw user documents (text, PDF, images, video, HTML, EML) into structured knowledge triples
(subject-predicate-object) with metadata, ready for RAG ingestion. It loads content with
**LangChain out-of-the-box document loaders** and extracts triples via **LLM reasoning**
(base Qwen3.5-4B in the LLM Service). It is triggered by authenticated file uploads.

## ADDED Requirements

### Requirement: File upload endpoint

The system SHALL expose an authenticated `POST /api/upload` endpoint that accepts
file uploads and processes them into structured triples.

#### Scenario: Successful upload

- **WHEN** an authenticated user sends `POST /api/upload` with a valid file (text, PDF, image, video, HTML, or EML)
- **THEN** the system processes the file, extracts triples, and returns HTTP 201 with the number of triples generated

#### Scenario: Unauthenticated upload

- **WHEN** a client sends `POST /api/upload` without a valid JWT token
- **THEN** the system responds with HTTP 401

#### Scenario: File too large

- **WHEN** a client uploads a file larger than 10MB
- **THEN** the system responds with HTTP 413 and a descriptive error message

#### Scenario: Unsupported file type

- **WHEN** a client uploads a file with an unsupported MIME type (not text, PDF, image, video, HTML, or EML)
- **THEN** the system responds with HTTP 422 with a list of supported types

### Requirement: Document parsing

The system SHALL load documents using **LangChain out-of-the-box document loaders**
(`langchain_community.document_loaders`), selecting the loader by MIME type, without
hand-rolling parsers unless no loader exists.

#### Scenario: PDF with text

- **WHEN** a PDF file contains extractable text
- **THEN** the system loads it with `PyPDFLoader` (or `PDFPlumberLoader`) and returns the page content

#### Scenario: PDF with scanned images

- **WHEN** a PDF file contains scanned images (no extractable text)
- **THEN** the system loads it with a LangChain `Unstructured*` loader that performs OCR (no bespoke Tesseract pipeline)

#### Scenario: Plain text document

- **WHEN** a plain-text file is uploaded
- **THEN** the system loads it with `TextLoader`

#### Scenario: HTML document

- **WHEN** an HTML file is uploaded
- **THEN** the system loads text content with `UnstructuredHTMLLoader`

#### Scenario: Email document

- **WHEN** an EML file is uploaded
- **THEN** the system loads headers and body with `UnstructuredEmailLoader`

#### Scenario: Image file

- **WHEN** an image file (PNG, JPG, etc.) is uploaded
- **THEN** the system loads it with `UnstructuredImageLoader`, which performs OCR out-of-the-box

#### Scenario: Video file

- **WHEN** a video file is uploaded
- **THEN** the system loads it with a LangChain video loader for downstream multimodal reasoning

### Requirement: Triple extraction

The system SHALL extract subject-predicate-object triples by passing the loaded content
to the **base Qwen3.5-4B model in the LLM Service (port 8003)**, which reasons over the
content and then emits JSON triples. Extraction is LLM-first, not rule-based or regex.

#### Scenario: LLM reasoning over loaded content

- **WHEN** a document is loaded and its content is sent to the LLM Service (base Qwen3.5-4B)
- **THEN** the model reasons over the content and returns a JSON array of triples `{"subject", "predicate", "object", "metadata"}`

#### Scenario: Medical recipe

- **WHEN** the loaded content describes a patient with diabetes taking metformin
- **THEN** the LLM emits triples such as `{"subject": "Patient", "predicate": "has", "object": "diabetes"}` and `{"subject": "Patient", "predicate": "takes", "object": "metformin"}`

#### Scenario: Multimodal input

- **WHEN** the loaded content comes from an image or video
- **THEN** the multimodal base Qwen3.5-4B reasons over that content and emits JSON triples with metadata

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
- **THEN** the LangChain loader handles decoding (with its fallback) and processing continues

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain unchanged. The ETL pipeline does not affect
service liveness.

#### Scenario: Health check unaffected by ETL

- **WHEN** a client sends `GET /health` while the ETL pipeline is processing documents
- **THEN** the system responds with HTTP 200 regardless of ETL activity
