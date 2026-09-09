# hybrid-store-rag Specification

## Purpose
The hybrid-store-rag capability provides the hybrid storage layer that combines
binary/document storage (local MongoDB with GridFS) with multimodal vector embeddings
(Chroma, local) to enable cross-modal semantic retrieval. It ingests JSONL triples from
Frame 2, generates 2048-dim multimodal embeddings, encrypts them with Fernet, and
provides Top-k retrieval for LLM context injection.

## Requirements

### Requirement: Document storage with per-user isolation

The system SHALL store original binaries in local MongoDB GridFS and document metadata in
MongoDB (local container) with per-user isolation via `user_id`.

#### Scenario: Store document metadata

- **WHEN** a user uploads a document through the ETL pipeline
- **THEN** the system stores the original binary in MongoDB GridFS and document metadata in MongoDB with fields: `_id`, `user_id`, `type`, `gridfs_id`, `triples_path`, `created_at`

#### Scenario: User-scoped document listing

- **WHEN** an authenticated user requests their documents
- **THEN** the system returns only documents belonging to that user's `user_id`

#### Scenario: Cross-user access attempt

- **WHEN** an authenticated user requests another user's document
- **THEN** the system responds with HTTP 404 (never revealing existence)

### Requirement: Vector embedding generation

The system SHALL generate multimodal vector embeddings from document content using
Qwen3-VL-Embedding-2B, embedding text, images and video into one shared 2048-dim space.

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

### Requirement: Encrypted vector storage

The system SHALL encrypt embeddings before storage with Fernet symmetric encryption.

#### Scenario: Embedding encryption

- **WHEN** an embedding is stored in Chroma
- **THEN** the vector is encrypted with Fernet before persistence

#### Scenario: Embedding decryption on retrieval

- **WHEN** embeddings are retrieved from the vector store
- **THEN** they are decrypted before being returned to the RAG service

### Requirement: Semantic retrieval with Top-k

The system SHALL provide semantic search with configurable Top-k retrieval.

#### Scenario: Semantic search

- **WHEN** a user sends a query
- **THEN** the system embeds the query with Qwen3-VL-Embedding-2B, searches the vector store cross-modally, and returns the Top-k most similar items across text/image/video (default k=3)

#### Scenario: Per-user retrieval

- **WHEN** a user performs a semantic search
- **THEN** results are filtered to only include that user's documents

### Requirement: RAG context injection

The system SHALL inject retrieved context into LLM prompts for augmented generation.

#### Scenario: Context-augmented response

- **WHEN** a user asks a question about their documents
- **THEN** the system retrieves relevant context via RAG and includes it in the LLM prompt
