## ADDED Requirements

### Requirement: On-demand multimodal embedding endpoint

The RAG Service SHALL expose `POST /embed` that returns a 2048-dimensional
query vector for text, an image, or a short video using
Qwen3-VL-Embedding-2B (or the configured mock embedder) in the shared
space. The vector SHALL NOT be written to Chroma or MongoDB. The service
SHALL NOT require the caller to pass a document id.

#### Scenario: Text embed succeeds

- **GIVEN** the RAG Service is running
- **WHEN** a client sends `POST /embed` with `modality` equal to `"text"` and non-empty `text`
- **THEN** the system responds HTTP 200 with `vector` of length 2048 and does not increase the Chroma collection count

#### Scenario: Image or video embed succeeds

- **GIVEN** the RAG Service is running
- **WHEN** a client sends `POST /embed` with `modality` equal to `"image"` or `"video"` and a non-empty payload
- **THEN** the system responds HTTP 200 with `vector` of length 2048 and does not store that vector

#### Scenario: Blank input is rejected

- **GIVEN** the RAG Service is running
- **WHEN** a client sends `POST /embed` with missing content for the declared modality
- **THEN** the system responds HTTP 422

#### Scenario: Correlation id is propagated

- **GIVEN** a request includes `X-Request-ID`
- **WHEN** `POST /embed` is handled
- **THEN** the same id appears in structured logs for that call

## MODIFIED Requirements

### Requirement: Vector embedding generation

The system SHALL generate multimodal vector embeddings from document content using
Qwen3-VL-Embedding-2B, embedding text, images and video into one shared 2048-dim space.
The same embedder SHALL also produce query vectors for sibling services via `POST /embed`
without persisting those query vectors.

#### Scenario: Embedding generation

- **WHEN** a document is ingested into the vector store
- **THEN** the system generates a 2048-dimensional vector using Qwen3-VL-Embedding-2B (default 2048; MRL-truncatable to 1024/512/256)

#### Scenario: Cross-modal embedding space

- **WHEN** documents of different modalities (text, image, video) are ingested
- **THEN** the system embeds them into one shared 2048-dim space so a text query can retrieve images or video

#### Scenario: Document chunking

- **WHEN** a document exceeds 1000 characters
- **THEN** the system splits it into chunks of 1000 characters with 200-character overlap
- **AND** stores each chunk in Chroma's `document` field alongside the vector, with metadata linking to the `gridfs_id`

#### Scenario: Query embed is not stored

- **WHEN** a sibling service sends `POST /embed` with text, an image, or a video
- **THEN** the system returns a 2048-dim vector and does not store that vector in Chroma
