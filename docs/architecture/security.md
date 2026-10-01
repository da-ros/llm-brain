# Security strategy

## Shift Left (in CI now)

| Gate | What it catches |
|------|-----------------|
| **ruff** | Style and obvious bugs before merge |
| **pytest** | Health, config fail-fast, provider resolution, JWT 401/200 |
| **Snyk test** | Vulnerable dependencies |
| **Snyk code test** | SAST on application code |

Workflow: `.github/workflows/ci.yml` on push/PR to `main` and `develop`.

## Shift Right (production, future)

Not in this MVP. When AWS exists: CloudWatch logs/metrics, API Gateway rate limits,
and TLS at the edge. Local MVP rate limits belong on the API Router (Frame 1.1).

## Data protection

- Passwords hashed with bcrypt; JWT never returns hashes.
- `GET /health` reports `status` and `llm_provider` only.
- Per-user isolation: document reads filter on `user_id` (404, not 403, so existence is not leaked).

### Application-level encryption (Fernet) — active since Frame 3

- **Scope**: rag-service only (`services/rag/vector_store.py`). `FERNET_KEY` is injected
  solely into rag-service in `docker-compose.yml`; other services do not read it.
- **What is encrypted at rest**: `chunk_text` (Chroma `document` field) and a ciphertext
  copy of each embedding (Chroma metadata `encrypted_vector`). The ANN index keeps the
  raw float vectors — HNSW/cosine cannot index ciphertext (spec:
  `openspec/specs/hybrid-store-rag/spec.md`).
- **Key**: `FERNET_KEY`, a url-safe base64 32-byte Fernet key. The local-dev default is
  derived as `urlsafe_b64(sha256("FERNET_KEY@TESIS_MESTRIA_UPS"))`.
- **Production**: override with a stable key from the secret store (AWS Secrets Manager
  in the ECS task definition). Never commit a production key. Rotating the key makes all
  previously stored ciphertext unreadable — there is no recovery path by design.
