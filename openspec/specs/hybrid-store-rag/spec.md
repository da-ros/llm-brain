# hybrid-store-rag Specification

## Purpose
The hybrid-store-rag capability provides the hybrid storage layer that combines
document storage (MongoDB Atlas) with vector embeddings (Chroma/Pinecone) to enable
semantic retrieval. It ingests JSONL triples from Frame 2, generates embeddings,
encrypts them with Fernet, and provides Top-k retrieval for LLM context injection.

## Requirements

### Requirement: Document storage with per-user isolation

The system SHALL store document metadata and triples in MongoDB Atlas with per-user
isolation via `user_id`.

#### Scenario: Store document metadata

- **WHEN** a user uploads a document through the ETL pipeline
- **THEN** the system stores document metadata in MongoDB with fields: `_id`, `user_id`, `type`, `original_path`, `triples_path`, `created_at`

#### Scenario: User-scoped document listing

- **WHEN** an authenticated user requests their documents
- **THEN** the system returns only documents belonging to that user's `user_id`

#### Scenario: Cross-user access attempt

- **WHEN** an authenticated user requests another user's document
- **THEN** the system responds with HTTP 404 (never revealing existence)

### Requirement: Vector embedding generation

The system SHALL generate vector embeddings from document text using sentence-transformers.

#### Scenario: Embedding generation

- **WHEN** a document is ingested into the vector store
- **THEN** the system generates a 384-dimensional vector using sentence-transformers/all-MiniLM-L6-v2

#### Scenario: Document chunking

- **WHEN** a document exceeds 1000 characters
- **THEN** the system splits it into chunks of 1000 characters with 200-character overlap

### Requirement: Encrypted vector storage

The system SHALL encrypt embeddings before storage with Fernet symmetric encryption.

#### Scenario: Embedding encryption

- **WHEN** an embedding is stored in Chroma/Pinecone
- **THEN** the vector is encrypted with Fernet before persistence

#### Scenario: Embedding decryption on retrieval

- **WHEN** embeddings are retrieved from the vector store
- **THEN** they are decrypted before being returned to the RAG service

### Requirement: Semantic retrieval with Top-k

The system SHALL provide semantic search with configurable Top-k retrieval.

#### Scenario: Semantic search

- **WHEN** a user sends a query
- **THEN** the system embeds the query, searches the vector store, and returns the Top-k most similar documents (default k=3)

#### Scenario: Per-user retrieval

- **WHEN** a user performs a semantic search
- **THEN** results are filtered to only include that user's documents

### Requirement: RAG context injection

The system SHALL inject retrieved context into LLM prompts for augmented generation.

#### Scenario: Context-augmented response

- **WHEN** a user asks a question about their documents
- **THEN** the system retrieves relevant context via RAG and includes it in the LLM prompt
