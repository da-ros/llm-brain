# OSS stack decision record (Frame 1)

See also `docs/architecture/stack.md`.

**Decision**: Local-only OSS stack with a single Qwen3.5-4B family.

**Rejected for MVP**: AWS Bedrock, Llama 3 8B, llama.rn + Llama 3.2 3B, MongoDB Atlas, Pinecone.

**Why**: context.txt is absolute truth — $0 budget, laptop Docker Compose, AWS is future work.
