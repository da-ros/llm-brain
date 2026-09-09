# Security strategy — Frame 1

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

## Data in this frame

- Passwords hashed with bcrypt; JWT never returns hashes.
- `GET /health` reports `status` and `llm_provider` only.
- Per-user isolation: document reads filter on `user_id` (404, not 403, so existence is not leaked).
- Fernet for embeddings is a later-frame concern; `FERNET_KEY` is reserved in `.env.example`.
