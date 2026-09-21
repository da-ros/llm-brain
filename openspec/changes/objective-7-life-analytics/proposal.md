## Why

Fragmented vital data is a core pain in the anteproyecto: sleep, meetings, and
focus live in silos, so the user never sees early correlations. Frames 3 and 6
already store documents and what-if traces, but there is no **premium web
dashboard** and no computed life metrics. Frame 7 adds Life Analytics:
ingest a diary or schedule (CSV, XLSX, DOCX, ICS, or an **image**), let **Qwen3.5-4B**
reason over that file and the rest of the user's stored context, compute
**at least two interactive correlations** (sleep vs productivity, meetings
vs focus time), and visualise both the charts and the model's inferences
in **React + Chart.js**. Every result is written to the DB.

## Context from Frame 6 and Frame 8

- **Frame 6 (Simulator, port 8007)**: deterministic what-if runs persisted in
  `simulations`. The dashboard **lists** that history via
  `GET /api/simulations` (already specified). Frame 7 does not change the
  tree.
- **Frame 8 (Privacy & Scam Shield)** is a **hard dependency** in
  `context.txt`. Frame 7 **consumes**
  `GET /api/shield/incidents` (premium, `user_id` scoped) returning
  `{ incidents: [{ id, created_at, severity, summary, source }] }`.
  Until that route is applied, the dashboard SHALL render an empty
  incidents panel (no crash).
- **Frame 1.1**: JWT, CORS, Router facade. **Frame 3**: RAG remains
  available; analytics does not embed Chroma.
- **Frame 4 (LLM, port 8003)**: Qwen3.5-4B base. Analytics calls
  `POST /chat` (temperature 0) to infer daily facts from free-form files
  and to write a narrative over the user's metrics plus RAG context.
- **OAuth federado is out of scope** (`context.txt`). “Connect Google
  Calendar” is a **file ingest** of CSV, XLSX, DOCX, ICS, or a photo of a
  diary or schedule, not live Google OAuth. LangChain loaders read the
  file. An image is OCR’d by the image loader, then the LLM infers the
  diary or schedule from that text and from the picture itself.

Frame 7 does **not** replace Simulator or Shield. It is the premium web
client plus a small analytics backend. Free tier has no web dashboard.

## What Changes

- Add **Analytics Service** (`services/analytics/`, port **8008**) that:
  - Ingests a diary or schedule as **CSV, XLSX, DOCX, ICS, or an image**
    (PNG, JPEG, WEBP) via LangChain loaders. Images go through the
    image loader’s OCR before inference
  - Calls **Qwen3.5-4B** to infer daily facts (sleep, productivity,
    meetings, focus, and any other life facts present) from the file
    **and** from RAG context of the user's other documents
  - Aligns numeric series by calendar day and computes **Pearson r** for
    (1) sleep_hours vs productivity_score and (2) meeting_hours vs
    focus_hours
  - Persists points, Pearson snapshots, and the LLM narrative in MongoDB
    (`life_metrics`, `analytics_snapshots`), isolated by `user_id`
  - A successful ingest **must** have called the LLM. LLM 5xx/timeout →
    502/504 and no partial write
- Add **premium web app** (`apps/web/`): React (English UI) + Chart.js
  with two interactive correlation charts, an LLM insights panel,
  simulation history (Frame 6), and a Shield incidents panel (Frame 8
  contract / empty state).
- Register MCP tool **`analytics_query`** on Agents Service wrapping
  Analytics HTTP. `reason_graph` is not rewritten.
- API Router (premium only):
  - `POST /api/analytics/ingest` (diary or calendar file) → 200
  - `GET /api/analytics/correlations` → 200 with both series + r + n
    and the latest LLM `insights`
  - `GET /api/analytics/metrics` → raw daily points for charts
  - `GET /api/analytics/insights` → latest narrative and inferred facts
- Rate limits: ingest **10 req/min**, correlations **30 req/min**.
  Correlation ID on every hop. Sync HTTP (no Kafka).
- Docker Compose: `analytics-service` on 8008; web app served locally
  (Vite dev / static nginx in Compose).
- Out of scope: Google OAuth, multilingual UI, Free-tier dashboard,
  Monte Carlo, live calendar sync, mobile analytics (Frame 10).

## Capabilities

### New Capabilities
- `analytics-service`: CSV/XLSX/DOCX/ICS/image ingest, LLM inference over the
  file and the user's other data, two Pearson correlations, per-user
  persistence, premium HTTP API.
- `life-analytics-web`: React + Chart.js premium dashboard (login, two
  interactive charts, simulation history, shield incidents empty-safe).

### Modified Capabilities
- `agents-service`: register MCP tool `analytics_query` wrapping
  Analytics HTTP.
- `api-router`: new premium analytics ingest/query routes; 401/403/404/429.

## Output

```
openspec/changes/objective-7-life-analytics/
├── output/
│   ├── diagrams/
│   │   ├── analytics-architecture.drawio
│   │   ├── analytics-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── analytics-service/spec.md
    ├── life-analytics-web/spec.md
    ├── agents-service/spec.md
    └── api-router/spec.md
```

## Impact

- New service: `services/analytics/` (FastAPI, Dockerfile, port 8008).
- New UI: `apps/web/` (React + Chart.js; placeholder README already
  exists from Frame 1).
- MongoDB collections `life_metrics` (daily points, including LLM-inferred
  fields) and `analytics_snapshots` (Pearson r, n, and LLM insights).
- API Router: analytics routes + `ANALYTICS_SERVICE_URL`.
- Agents Service: one extra MCP tool; graphs unchanged.
- Frame 6 list endpoint reused; Frame 8 incidents endpoint consumed
  with graceful empty state.
- Kafka unchanged. No change to Simulator tree or RAG schema.
- Docker Compose: analytics-service + optional `web` static service;
  `LLM_SERVICE_URL` and `RAG_SERVICE_URL`.
- Out of scope: OAuth, Free tier, AWS, Monte Carlo. The LLM call is in
  scope.

## Execution Order

1. Analytics Service skeleton (config, health, correlation ID, Dockerfile).
2. LangChain load of CSV/XLSX/DOCX/ICS/image (OCR on images), then LLM inference of daily facts
   plus a narrative grounded in RAG context.
3. Pearson on the inferred series; MongoDB persistence + isolation.
4. MCP `analytics_query`; API Router premium routes + rate limits.
5. React + Chart.js dashboard (login, two charts, LLM insights,
   simulations, incidents).
6. Tests (ingest of csv/xlsx/docx/image, r formula, LLM called, 403/404, empty Shield).
7. `output/` diagrams and justificacion with structured-log examples.
