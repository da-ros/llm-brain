# Local endpoint testing — cURL guide (Postman-ready)

All commands target the Docker Compose stack on `localhost`. Every cURL below can be
pasted directly into Postman (**Import → cURL**). Suggested collection variables:

| Variable | Value |
|----------|-------|
| `base_url` | `http://localhost:8000` |
| `token_free` | JWT, `subscription_tier: "free"` |
| `token_premium` | JWT, `subscription_tier: "premium"` |

---

## 0. Mint JWT tokens

The API Router validates HS256 JWTs signed with `JWT_SECRET_KEY`. The compose default
is `local-dev-secret-not-for-production`. There is no login endpoint in the MVP —
tokens are minted out-of-band (this is also how the mobile app will receive them later).

```bash
python3 -c "
import jwt, datetime
secret = 'local-dev-secret-not-for-production'
for tier in ('free', 'premium'):
    payload = {
        'sub': 'user-demo',
        'subscription_tier': tier,
        'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
    }
    print(tier, jwt.encode(payload, secret, algorithm='HS256'))
"
```

Alternative: build the token on [jwt.io](https://jwt.io) with the same secret and payload.

Claims used by the router (`services/api-router/auth.py`):

- `sub` — user_id (required, else 401)
- `subscription_tier` — `free` | `premium` (missing → `free`)
- `exp` — expiry

Tier behavior:

| Endpoint | free | premium |
|----------|------|---------|
| `POST /api/chat` | direct LLM (`/generate`), no RAG, no Kafka | Agents Razonador + RAG + Kafka `session.turn.completed` |
| `POST /api/upload`, `POST /api/finetune`, `POST /api/sessions/end` | 403 | ✅ |
| `POST /api/simulate`, `GET /api/simulations*` | 403 | ✅ |
| `POST /api/shield/scan`, `GET /api/shield/*` | 403 | ✅ |
| `GET /api/documents*`, `GET /tasks/*` | ✅ | ✅ |

Rate limits (per minute, from compose): upload 10, chat 30, tasks 60, simulate 10,
shield scan 30.

---

## 1. Smoke — healthchecks (no auth)

```bash
# API Router
curl -s http://localhost:8000/health

# ETL (pipeline itself is Kafka-driven; only health is HTTP)
curl -s http://localhost:8001/health

# RAG
curl -s http://localhost:8002/health

# LLM (mock provider)
curl -s http://localhost:8003/health

# Fine-Tune
curl -s http://localhost:8004/health

# Agents
curl -s http://localhost:8006/health

# Simulator
curl -s http://localhost:8007/health

# Shield
curl -s http://localhost:8009/health
```

---

## 2. API Router (`base_url` = `http://localhost:8000`)

All requests may send `X-Request-ID: <uuid>` — optional; the router mints one if absent
and echoes it back in the response header.

### 2.1 Chat — free tier (direct LLM path)

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer {{token_free}}" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hola, ¿qué recuerdas sobre mí?", "use_rag": true}'
```

Expected: `200` with `context_used: false` (free skips RAG), `response` from the
mock LLM.

### 2.2 Chat — premium tier (Agents Razonador path)

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer {{token_premium}}" \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Cómo voy mis finanzas este mes?", "use_rag": true, "session_id": "sess-demo-1"}'
```

Expected: `200` with `sources`, `assumptions`, `session_id`. Side effects: Kafka
`session.turn.completed` published in the background.

### 2.3 Upload document — premium only (async via Kafka)

Create a small sample file first:

```bash
printf 'Mi meta este mes es ahorrar 200 dolares. Reunion con Juan el viernes a las 10am.\n' > /tmp/notas-llm-brain.txt
```

```bash
curl -s -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer {{token_premium}}" \
  -F "file=@/tmp/notas-llm-brain.txt"
```

Expected: `202` with:

```json
{"correlation_id": "<uuid>", "status": "processing", "message": "..."}
```

Constraints: MIME detected by python-magic (txt/md/pdf/csv allowed), max 10MB,
premium only, GridFS + Kafka `file.uploaded`.

### 2.4 Poll task status (ETL pipeline)

Use the `correlation_id` from the upload response:

```bash
curl -s http://localhost:8000/tasks/<correlation_id> \
  -H "Authorization: Bearer {{token_premium}}"
```

Expected flow: `in_progress` → `completed` (ETL consumes `file.uploaded`, calls LLM
`/extract` for triples, writes `data/triples/<user_id>/<correlation_id>.jsonl`, then
RAG `/ingest` populates Chroma). Foreign tasks → 403; unknown → 404.

### 2.5 Documents (RAG index, per-user isolation)

```bash
curl -s "http://localhost:8000/api/documents" \
  -H "Authorization: Bearer {{token_premium}}"

curl -s "http://localhost:8000/api/documents/<doc_id>" \
  -H "Authorization: Bearer {{token_premium}}"
```

Wrong-user or missing doc → 404 (existence is never leaked).

### 2.6 Decision-Support Simulator — premium only

```bash
curl -s -X POST http://localhost:8000/api/simulate \
  -H "Authorization: Bearer {{token_premium}}" \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué pasa si dejo de pagar el gimnasio?", "variables": {"monthly_spend": 40}}'
```

```bash
curl -s "http://localhost:8000/api/simulations" \
  -H "Authorization: Bearer {{token_premium}}"

curl -s "http://localhost:8000/api/simulations/<simulation_id>" \
  -H "Authorization: Bearer {{token_premium}}"
```

### 2.7 Privacy & Scam Shield — premium only

```bash
curl -s -X POST http://localhost:8000/api/shield/scan \
  -H "Authorization: Bearer {{token_premium}}" \
  -H "Content-Type: application/json" \
  -d '{"text": "Gana $5000 diario sin invertir, solo envia tu cedula por WhatsApp", "source": "whatsapp"}'
```

```bash
curl -s "http://localhost:8000/api/shield/incidents" \
  -H "Authorization: Bearer {{token_premium}}"

curl -s "http://localhost:8000/api/shield/guidelines" \
  -H "Authorization: Bearer {{token_premium}}"
```

`content_base64` may be sent instead of `text` for file scans (max 20MB).

### 2.8 Session end + manual Fine-Tune trigger — premium only

```bash
# End a chat session → Evaluador finalizes feedback
curl -s -X POST http://localhost:8000/api/sessions/end \
  -H "Authorization: Bearer {{token_premium}}" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-demo-1"}'

# Trigger a ready batch (batch must exist and be ready, else 409)
curl -s -X POST http://localhost:8000/api/finetune \
  -H "Authorization: Bearer {{token_premium}}" \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "batch-demo-1"}'
```

---

## 3. Downstream services — direct (no JWT)

Downstream services trust the API Router in the MVP (no service-to-service JWT).
Direct calls are useful for isolating failures per service.

### 3.1 LLM Service — `:8003`

```bash
curl -s -X POST http://localhost:8003/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Resumen: mi meta es ahorrar 200 dólares", "user_id": "user-demo", "tier": "premium"}'

curl -s -X POST http://localhost:8003/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hola"}], "user_id": "user-demo", "tier": "free"}'

curl -s -X POST http://localhost:8003/extract \
  -H "Content-Type: application/json" \
  -d '{"content": "Juan vive en Quito. Ana trabaja en UPS.", "user_id": "user-demo"}'
```

With `QWEN_MOCK=true` responses are deterministic mocks — no model download.

### 3.2 RAG Service — `:8002`

```bash
# Vector search (user_id isolation)
curl -s "http://localhost:8002/search?query=meta%20ahorro&user_id=user-demo&k=3"

# LLM-facing context block
curl -s "http://localhost:8002/context?query=meta%20ahorro&user_id=user-demo"

# On-demand embed (2048-dim with real model; deterministic hash vector in mock)
curl -s -X POST http://localhost:8002/embed \
  -H "Content-Type: application/json" \
  -d '{"modality": "text", "text": "meta de ahorro"}'

# Ingest distilled triples (called by the pipeline; handy to re-run manually)
curl -s -X POST http://localhost:8002/ingest \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "doc_id": "doc-demo-1", "triples_path": "data/triples/user-demo/<correlation_id>.jsonl"}'

# Documents index
curl -s "http://localhost:8002/documents?user_id=user-demo"

# Cleanup embeddings for a doc
curl -s -X DELETE "http://localhost:8002/embeddings/<doc_id>?user_id=user-demo"
```

### 3.3 Agents Service — `:8006`

```bash
curl -s -X POST http://localhost:8006/reason \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "subscription_tier": "premium", "message": "¿Cómo voy mis finanzas?", "session_id": "sess-demo-1"}'

curl -s http://localhost:8006/mcp/tools

curl -s http://localhost:8006/batches

curl -s http://localhost:8006/batches/<batch_id>

curl -s -X POST http://localhost:8006/batches/<batch_id>/trigger \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "subscription_tier": "premium"}'

curl -s -X POST http://localhost:8006/sessions/end \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "session_id": "sess-demo-1", "subscription_tier": "premium"}'

curl -s http://localhost:8006/interactions/<correlation_id>
```

### 3.4 Simulator Service — `:8007`

Requires premium via body or `X-Subscription-Tier` header (enforced by
`ensure_premium`):

```bash
curl -s -X POST http://localhost:8007/simulate \
  -H "Content-Type: application/json" \
  -H "X-Subscription-Tier: premium" \
  -d '{"user_id": "user-demo", "question": "¿Y si gano 20% más?", "subscription_tier": "premium"}'

curl -s "http://localhost:8007/simulations?user_id=user-demo"

curl -s "http://localhost:8007/simulations/<simulation_id>"
```

### 3.5 Shield Service — `:8009`

```bash
curl -s -X POST http://localhost:8009/scan \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "text": "Envia tu cedula para ganar dinero", "source": "whatsapp"}'

curl -s "http://localhost:8009/incidents?user_id=user-demo"

curl -s "http://localhost:8009/incidents/<incident_id>?user_id=user-demo"

curl -s "http://localhost:8009/guidelines"
```

### 3.6 Fine-Tune Service — `:8004`

```bash
curl -s -X POST http://localhost:8004/train \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-demo", "dataset_path": "data/finetune_batches/<batch_id>/dataset.jsonl"}'

curl -s http://localhost:8004/status/<job_id>
```

With `LORA_MOCK=true` the job completes in milliseconds (no GPU).

### 3.7 ETL Service — `:8001`

No HTTP pipeline API — it consumes Kafka `file.uploaded`. Only:

```bash
curl -s http://localhost:8001/health
```

Observe the pipeline with `docker compose logs -f etl-service`.

---

## 4. Suggested test order (smoke script)

1. Healthchecks (section 1) — all 8 return `200`.
2. Mint tokens (section 0).
3. `POST /api/chat` free → 200 mock response.
4. `POST /api/chat` premium → 200 with sources/assumptions.
5. `POST /api/upload` (sample txt) → 202, capture `correlation_id`.
6. Poll `GET /tasks/<correlation_id>` → `completed`; check
   `data/triples/user-demo/` and `docker compose logs -f etl-service`.
7. `GET /api/documents` → the uploaded doc indexed.
8. `POST /api/chat` premium asking about the doc content → `context_used: true`.
9. `POST /api/simulate` → scenarios; `GET /api/simulations/<id>`.
10. `POST /api/shield/scan` scam text → incident flagged; `GET /api/shield/incidents`.
11. Negative tests: no token → 401; free token on premium endpoints → 403;
    other user's `doc_id` → 404.
