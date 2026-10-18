## Context

See proposal.md — Why. RAG already embeds user documents (2048-dim) but
does not classify inbound messages. Frame 7 already reserved
`GET /api/shield/incidents`. Frame 8 fills `services/shield/` on port
**8009** and adds RAG `POST /embed`.

Constraints from `context.txt`: heuristics + embedding similarity on
email/SMS/messages; popup alerts; persist incidents; no supervised
full-scale fraud models; no voice impersonation; no OAuth; Kafka only for
heavy async work; correlation id; `user_id` isolation; MCP `scan_message`;
clients talk only to the Router; Frame 8 depends on 1.1 + 3 and runs in
parallel with Frame 6. Free tier has no cloud RAG, so Shield is premium.

## Goals / Non-Goals

**Goals:**
- Accept pasted text, an image, or a short video.
- Heuristics and cosine similarity are evidence. Qwen3.5-4B decides likelihood.
- Explainability on every 200 scan (`reasons[]` includes the model rationale).
- Persist alerts only when the LLM sets `alert`; list in the Frame 7 JSON envelope.
- RAG query embed (text, image, video) without storing the vector.
- MCP `scan_message`; Router facade; web popup.

**Non-Goals:**
- Do not train a supervised fraud model or open Chroma from Shield.
- Do not load Qwen weights inside Shield (HTTP to port 8003).
- Do not raise an alert from heuristics alone when the LLM says it is safe.
- Do not succeed a scan that skipped the LLM.
- Do not intercept live SMS/mail or detect voice impersonation.
- Do not auto-scan premium chat turns.
- Do not give Free-tier users Shield.
- Do not use Kafka for scan.

## Decisions

### 1. Dedicated Shield Service (port 8009)

**Decision**: FastAPI `services/shield/` on 8009 (8007 simulator, 8008
analytics). Fill the Frame 1 placeholder.

**Alternatives considered**:
- Logic in API Router — rejected (facade).
- Logic in Agents — rejected (parallel with Frame 6; must work if Agents
  is down).
- Logic in RAG — rejected (RAG is retrieval).

### 2. RAG `POST /embed` for every modality

**Decision**: Add `POST /embed` on RAG 8002 with `modality` of `text`,
`image`, or `video`. The vector is 2048-dim and is not stored. Shield
caches corpus text vectors at startup. A scan embeds the submitted text,
image, or video once and cosines in-process against that gallery
(cross-modal, same space as Frame 3).

**Alternatives considered**:
- Load Qwen3-VL-Embedding-2B inside Shield — rejected (duplicate ~2B
  weights on the laptop).
- Reuse `GET /search` on the user's Chroma — rejected (compares to
  personal notes, not a known-scam gallery).
- System `user_id` corpus in Chroma — rejected (leaks a shared
  collection into per-user search; Shield would still need Chroma access
  patterns).

### 3. Evidence first, then the LLM decides

**Decision**: If the upload is an image, **OCR it first** (LangChain
`UnstructuredImageLoader`). Screenshots of SMS or mail are the common
case, so heuristics and the text-corpus cosine run on the OCR string, not
only on pixels. An empty OCR result is recorded as `ocr_empty` and does
not skip the LLM. Video is not OCR’d.

Then collect evidence and make **one** `POST /chat` (temperature 0) to
Qwen3.5-4B. The prompt includes pasted text and/or OCR text, the image or
video bytes, fired heuristic ids, and the nearest corpus id plus cosine.
The model returns JSON: `likelihood` (0–1), `alert`, `severity`
(`none`|`medium`|`high`), `summary`, `rationale`.

Suggested bands the prompt asks the model to follow (the model may
depart when the media contradicts the heuristics; that departure is the
point of calling it):

| Evidence the prompt shows | Typical severity |
|---------------------------|------------------|
| Strong scam cues (several heuristics or cosine ≥ 0.90) | `high` |
| One heuristic or cosine ≥ 0.80 | `medium` |
| Ham nearest neighbour and no heuristics | `none` |

`alert` is whatever the model returns. Heuristics do not override it.
If embed fails, still call the LLM and add reason `embedding_unavailable`.
If the LLM fails or JSON is invalid after one retry → 502/504, no persist.

**Rationale**: `context.txt` requires heuristics and embedding similarity.
Those stay visible in `reasons`. The value-module contract is that the
LLM reasons about the likelihood, including on an image or a video that
heuristics cannot read.

### 4. Deterministic heuristic pack

**Decision**: Case-insensitive rules over the raw text (and extracted
URLs). IDs (stable for explainability):

| id | Fires when |
|----|------------|
| `urgency` | act now / immediately / account suspended / within 24 hours |
| `credential` | verify password / confirm ssn / one-time pin / update billing |
| `money` | gift card / wire transfer / bitcoin / wallet address |
| `short_url` | bit.ly, t.co, tinyurl, lnkd.in |
| `lookalike_host` | paypa1, g00gle, micros0ft, app1e in a URL host |
| `prize` | lottery / you have won / claim your prize |

No ML weights. English + common Spanish tokens (`urgente`, `verifique
su cuenta`, `premio`) so Spanish documents still flag.

### 5. 30-item in-repo corpus

**Decision**: `data/shield/corpus.jsonl` — 30 lines
`{id, label: phishing|scam|ham, source: email|sms|message, text}`.
About 20 positive / 10 ham. Used as similarity gallery **and** pytest
fixtures (cronograma: 30 test messages). Not user PII.

### 6. Persist alerts only; Frame 7 list shape

**Decision**: Insert `shield_incidents` only when the LLM sets `alert`
true. `GET /incidents` maps to
`{ incidents: [{ id, created_at, severity, summary, source }] }`.
Unique `correlation_id`. Non-alerts are logged, not stored. `source` is
`email`, `sms`, `message`, `image`, or `video`.

### 7. MCP and web without rewriting chat

**Decision**: `scan_message` → Shield `POST /scan`. Graphs unchanged.
Web: English textarea, source select, and a file input for image or
video. Popup on `alert`. If Frame 7 dashboard is absent, a minimal
`/shield` page in `apps/web` is enough; Frame 7 later embeds the same
calls in its incidents panel. Video uploads are capped (default 20 MB).

### 8. Guidelines as static text

**Decision**: `GET /guidelines` returns a short English responsible-use
notice (assistive only, test messages, no guarantee). No extra CMS.

## Data Flow

### Scan (sync)

```
1. Client POST /api/shield/scan {text?, file?, source}
2. API Router: JWT ✓, premium, 30/min, X-Request-ID
3. Router HTTP POST shield-service:8009/scan
4. If correlation_id exists → return stored scan result
5. If image → OCR; heuristics run on pasted text and on OCR text
6. RAG POST /embed of that text (and of the image/video) → cosine vs corpus
7. HTTP POST LLM 8003 /chat (text and/or OCR and/or image/video + evidence, temperature 0)
8. alert = model.alert; if true → upsert shield_incidents
9. HTTP 200 {alert, likelihood, severity, summary, reasons, llm_used, incident_id?}
   (no Kafka)
```

### List / guidelines / MCP / web

```
GET /api/shield/incidents  → {incidents: [...]}  (200 even if empty)
GET /api/shield/guidelines → {text}
POST agents /mcp/tools/scan_message → Shield POST /scan
SPA submit → popup if alert; refresh incidents list
```

### Errors

```
Free / no JWT        → 403 / 401
No text and no file → 422
File over 20 MB     → 422
31st scan/min       → 429
LLM 5xx / bad JSON  → 502/504, no persist
Cross-user id       → 404
```

## Configuration

```
SHIELD_HOST=0.0.0.0
SHIELD_PORT=8009
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://host.docker.internal:8003
LLM_TEMPERATURE=0
MONGODB_URI=...
SIMILARITY_THRESHOLD=0.80
MAX_UPLOAD_BYTES=20971520
CORPUS_PATH=/app/data/shield/corpus.jsonl
```

Router: `SHIELD_SERVICE_URL=http://shield-service:8009`
Agents: `SHIELD_SERVICE_URL=http://shield-service:8009`
Rate limit: `RATE_LIMIT_SHIELD_SCAN=30`

## Data model (MongoDB)

```
shield_incidents:
  { _id, user_id, correlation_id (unique),
    source: email|sms|message|image|video,
    likelihood, llm_used,
    severity: medium|high,
    summary, reasons[],
    created_at }
```

All queries filter `user_id`. Unique index on `correlation_id`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| A screenshot has no pasted text | OCR the image and run heuristics on that string; the LLM still sees the pixels |
| Model disagrees with a heuristic | The model's `alert` wins; the heuristic stays in `reasons` |
| RAG embed latency plus LLM | Corpus cached; one embed and one chat call; 30s ceiling; 504 on timeout |
| Video size | 20 MB cap; larger files are 422 |
| Spanish/English mix | Heuristic tokens in both; embeddings are multilingual |
| Frame 7 not applied | Incidents API still 200 `[]`; minimal `/shield` page |
| Dual-use of a “scanner” | Guidelines + premium JWT + local test corpus only |

## Migration Plan

1. Deploy RAG `POST /embed` (backward compatible).
2. Deploy Shield Service + Router routes + MCP tool.
3. Rollback: stop 8009; Router maps 502; chat/simulate unchanged.
4. Frame 7 dashboard then binds to the live incidents list.

## Open Questions

None that block specs or tasks. Extra heuristic ids (attachments, QR)
can wait; the six ids above cover the cronograma samples.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Chain of responsibility** | Heuristic pack | Independent rules append `reasons` |
| **Strategy** | Heuristics, embeddings, LLM | Three evidence steps, one verdict |
| **Facade** | API Router | Clients never address port 8009 |
| **Protocol (MCP tools)** | `scan_message` | Same contract as Frame 5/6/7 tools |
| **Flyweight / cache** | Corpus vectors at startup | Avoid re-embedding 30 lines |
| **Idempotent command** | `correlation_id` unique index | Safe retries |
| **Graceful degradation** | Embed 5xx | LLM still runs; a failed LLM does not |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Heuristics, cosine, repository, and guidelines are separate |
| **O** | New heuristic id without changing HTTP routes |
| **L** | Email/SMS/message share one scan DTO |
| **I** | `/scan` vs `/incidents` vs `/guidelines` vs MCP |
| **D** | Shield depends on RAG `/embed` and LLM `/chat` URLs, not Chroma or weights |
