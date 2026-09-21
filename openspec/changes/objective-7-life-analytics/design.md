## Context

See proposal.md — Why. Frame 6 already persists what-if runs and exposes
`GET /api/simulations`. There is no diary/calendar ingest, no computed
sleep/productivity or meetings/focus series, and `apps/web/` is a
placeholder. Frame 8 (Shield) is not proposed yet; this design consumes a
fixed incidents contract and degrades when it is absent.

Constraints from `context.txt`: React + Chart.js; ≥2 interactive
correlations; Google Calendar **or** personal diary; each module writes
results to the DB; English UI; OAuth federado out of scope; Free tier has
no web dashboard; clients talk only to the API Router; MCP tool
`analytics_query`; Frame 7 depends on Frame 6 and Frame 8; Kafka is for
heavy async work (analytics ingest of a CSV is sync).

## Goals / Non-Goals

**Goals:**
- Analytics Service on port 8008: ingest + LLM inference + Pearson + persistence.
- Accept CSV, XLSX, DOCX, ICS, and images (PNG, JPEG, WEBP). The LLM infers diary/schedule facts.
- Two required Pearson pairs (sleep/productivity, meetings/focus) plus an
  LLM narrative over those series and the user's other RAG context.
- Premium React dashboard with Chart.js, insights, simulation history, Shield panel.
- MCP `analytics_query` on the existing Agents host.
- Router facade + rate limits (ingest 10/min, correlations 30/min).

**Non-Goals:**
- Do not implement Google OAuth or live Calendar sync.
- Do not replace Pearson with a stochastic model (Monte Carlo stays out).
- Do not succeed an ingest that skipped the LLM.
- Do not put Pearson or the narrative in the browser.
- Do not rewrite `reason_graph` or the Simulator tree.
- Do not implement Shield detection (Frame 8); only consume incidents.
- Do not ship a Free-tier dashboard or multilingual UI.
- Do not load Qwen weights inside Analytics (HTTP to port 8003).

## Decisions

### 1. Backend service + SPA (not SPA-only)

**Decision**: New FastAPI `services/analytics/` on port **8008** plus
`apps/web/` (Vite + React). Pearson and the LLM call run on the server so
MCP and tests share one path. The SPA plots points and shows the narrative.

**Alternatives considered**:
- Charts only in the browser from raw CSV — rejected (`analytics_query`
  and “write results to the DB” need a service).
- Analytics inside Simulator 8007 — rejected (different bounded context).
- Analytics inside API Router — rejected (Router is a facade).

### 2. Diary and schedule files, then the LLM infers

**Decision**: `POST /ingest` accepts `.csv`, `.xlsx`, `.docx`, `.ics`,
and an image (`.png`, `.jpg`, `.jpeg`, `.webp`). LangChain loaders
(`CSVLoader`, Unstructured Excel/Word, ICS text, `UnstructuredImageLoader`
with OCR) turn the file into text. A photo of a handwritten or printed
diary is OCR’d first; the LLM also receives the image bytes so it can
read what OCR missed. A structured CSV may fill columns directly. A prose
DOCX, a loose spreadsheet, or OCR text still counts: **one** `POST /chat`
to Qwen3.5-4B (temperature 0) receives the extracted text, the image when
present, **and** RAG Top-k context for that `user_id`, and returns JSON days
(`date`, `sleep_hours`, `productivity_score`, `meeting_hours`,
`focus_hours`, plus `other_facts[]`) and a short English `narrative`.
Hours outside 0–24 or a score outside 1–10 are dropped for that field,
not for the whole file. Empty or unreadable files are 422. LLM failure
is 502/504 and no write. No Google APIs.

**Rationale**: The anteproyecto allows a calendar export or a personal
diary. `context.txt` already uses LangChain loaders for any file and
Qwen3.5-4B to reason. OAuth stays out of scope.

### 3. Pearson r on the inferred series

**Decision**: After the LLM (and any structured columns) produce daily
numbers, keep dates where **both** series are present. Pearson is still
required; it does not replace the narrative.
Sample Pearson:

```
r = Σ(x-x̄)(y-ȳ) / sqrt(Σ(x-x̄)² Σ(y-ȳ)²)
```

`n < 2` or zero variance → `r: null`, `status: "insufficient"`. Same
points always yield the same r (float rounded to 4 decimals in the JSON).
No p-values, no bootstrap.

**Alternatives considered**: Spearman / ML regressors — rejected (overkill;
thesis asks for interactive correlations, not a stats paper).

### 4. Upsert daily metrics, snapshot on ingest

**Decision**: `life_metrics` unique `(user_id, date)`. Re-ingest of the
same day replaces fields the new file actually inferred. After a 200
ingest, write `analytics_snapshots` with both Pearson pairs, `narrative`,
`inferred_facts`, and `llm_used: true`.

### 5. Frame 8 incidents contract (consumed, not owned)

**Decision**: Dashboard calls `GET /api/shield/incidents`. Expected 200
body: `{incidents: [{id, created_at, severity, summary, source}]}`.
404/501/network → empty panel. Frame 8 MUST implement this path; Frame 7
MUST NOT 500 if it is missing.

### 6. MCP without changing chat graphs

**Decision**: `analytics_query` → Analytics `GET /correlations`.
`reason_graph` unchanged.

### 7. Web stack

**Decision**: Vite + React (English) + Chart.js scatter (x = sleep or
meetings, y = productivity or focus) plus an insights panel for the LLM
narrative. The file input accepts `.csv`, `.xlsx`, `.docx`, `.ics`, and images.
JWT from `POST /api/auth/login`
(existing Frame 1/1.1 auth) stored in `sessionStorage`. Dev proxy `/api`
→ Router `:8000`. Compose optional nginx for `apps/web/dist`.

## Data Flow

### Ingest + correlate (sync)

```
1. Client (SPA) POST /api/analytics/ingest (kind, file)
2. API Router: JWT ✓, premium, 10/min, X-Request-ID
3. Router HTTP POST analytics-service:8008/ingest
4. LangChain load CSV/XLSX/DOCX/ICS, or OCR an image → text
5. RAG GET /search (user_id) + LLM POST /chat (temperature 0)
   → daily facts + narrative
6. Upsert life_metrics; Pearson; analytics_snapshots (insights included)
7. HTTP 200 {rows_upserted, correlations, insights, llm_used}
   (no Kafka, no OAuth)
```

### Dashboard load

```
1. SPA login → JWT
2. GET /api/analytics/correlations → two Chart.js scatters + insights panel
3. GET /api/simulations → history panel (Frame 6)
4. GET /api/shield/incidents → incidents or empty state (Frame 8)
```

### MCP

```
POST agents:8006/mcp/tools/analytics_query
  → GET analytics:8008/correlations (same X-Request-ID)
```

### Errors

```
Free / no JWT     → 403 / 401
Unreadable/empty file → 422, no write, no LLM
LLM 5xx / bad JSON → 502/504, no write
11th ingest/min   → 429
31st GET corr/min → 429
Cross-user id     → 404
Analytics 5xx     → Router 502; MCP 502/504
Shield missing    → UI empty panel
```

## Configuration

```
ANALYTICS_HOST=0.0.0.0
ANALYTICS_PORT=8008
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://llm-service:8003
LLM_TEMPERATURE=0
MONGODB_URI=...
MONGODB_DB=llm_brain
```

Router: `ANALYTICS_SERVICE_URL=http://analytics-service:8008`
Agents: `ANALYTICS_SERVICE_URL=http://analytics-service:8008`
Rate limits: `RATE_LIMIT_ANALYTICS_INGEST=10`, `RATE_LIMIT_ANALYTICS_QUERY=30`
Web: `VITE_API_BASE_URL=` (same-origin `/api` via proxy)

## Data model (MongoDB)

```
life_metrics:
  { _id, user_id, date (YYYY-MM-DD),
    sleep_hours?, productivity_score?,
    meeting_hours?, focus_hours?,
    updated_at }

analytics_snapshots:
  { _id, user_id, correlation_id,
    pairs: {
      sleep_productivity: { r, n, status, points[] },
      meetings_focus:     { r, n, status, points[] }
    },
    narrative, inferred_facts[], llm_used, model_id,
    generated_at }
```

Unique index `(user_id, date)` on `life_metrics`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Frame 8 not applied yet | Empty incidents panel; dashboard still ships OE7 |
| Tiny n makes r noisy | `insufficient` when n < 2; UI never invents r |
| Prose files have no columns | LLM infers days; unreadable files are 422 |
| LLM JSON is malformed | One retry, then 502 and no write |
| ICS dialects | Loader text is passed to the LLM; do not require a perfect ICS grammar |
| JWT in the browser | sessionStorage; HTTPS is future/out of MVP |
| Pearson on outliers | Use the numbers the LLM (or the CSV) produced; no winsorizing |
| Two extra Compose services (analytics + web) | Matches existing one-service-per-module pattern |

## Migration Plan

1. Deploy Analytics Service via Docker Compose.
2. Add Router routes and Agents tool (new paths; chat unchanged).
3. Build `apps/web` against local Router.
4. Rollback: stop analytics + web; API chat/simulate keep working.

## Open Questions

None that block specs or tasks. Pomodoro timers mentioned in the
anteproyecto alcance are **not** in `context.txt` Frame 7 description
(two correlations + dashboard); they stay out of this frame.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Facade** | API Router | Clients never address port 8008 |
| **Protocol (MCP tools)** | `analytics_query` | Same contract as Frame 5/6 tools |
| **Repository** | `life_metrics` / snapshots | Per-user persistence |
| **DTO / snapshot** | `analytics_snapshots` | Traceable r at ingest time |
| **Graceful degradation** | Shield panel | Frame 7 usable without Frame 8 UI data |
| **BFF-less SPA** | `apps/web` | Talks only to the gateway |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Loader, LLM client, Pearson, repository, and React views are separate |
| **O** | New `kind` or pair without changing chart components' data contract (`points`, `r`, `n`) |
| **L** | CSV, XLSX, DOCX, ICS, and an OCR’d image all yield text the LLM can infer from |
| **I** | Ingest vs correlations vs metrics vs MCP query |
| **D** | Analytics depends on RAG and LLM URLs; the web depends on Router JSON |
