## Context

> **Current runtime.** This file keeps the decision text of this frame. Before citing it as the running system, read `docs/architecture/current-runtime.md`.


See proposal.md — Why. Frames 1 through 6 and Frame 8 already expose
the product through the API Router. `apps/web/` is the Encefalus user
interface for those routes. The anteproyecto names objetivo 7 Life
Analytics. That work is the Analytics screen and `services/analytics/`.
The frame as delivered is the whole interface.

Constraints from `context.txt`: English UI; clients talk only to the
API Router; OAuth federado is out of scope; each module writes its own
results to the DB; at least two interactive correlations (sleep vs
productivity, meetings vs focus); Pearson stays on the server; Kafka
is for heavy async work, not for drawing a screen.

## Goals / Non-Goals

**Goals:**
- Welcome screen before the product. Sign up and sign in with name,
  email, and password. A new account is free.
- Home at `/`, then Brain, Memory, Decisions, Analytics, Shield,
  Learning, and Settings.
- Each screen that shows product data is filled from the matching
  router JSON. Empty and error states come from that response.
- Free: Brain chat, the chat list, and Settings. Premium: every screen.
- Analytics screen: two interactive scatters, `r` and `n`, the narrative,
  the stored days, and a file ingest. The browser does not compute `r`.
- Analytics Service on port 8008 for that screen, plus MCP
  `analytics_query` for Agents. The browser does not call either.

**Non-Goals:**
- Do not add Apple or Google sign-in.
- Do not implement Google OAuth or live Calendar sync.
- Do not compute Pearson, the narrative, the decision tree, or a shield
  verdict in the browser.
- Do not let the browser call ports 8002–8009.
- Do not rewrite `reason_graph`, the Simulator tree, or Shield detection.
- Do not ship a multilingual UI or the mobile app.
- Do not wire `POST /api/sessions/end`.

## Decisions

### 1. One web app, one router

**Decision**: `apps/web/` is a React app (TanStack Start, Vite, Tailwind).
Dev server proxies `/api` to `localhost:8000`. Compose nginx (profile
`web`, host port 5173) does the same to `api-router:8000`. The JWT and
the account JSON live in `sessionStorage`. No token means the welcome
screen. A token means the shell.

**Alternatives considered**:
- A separate page per service — rejected. One product, one origin.
- The browser calling Analytics, RAG, or Shield directly — rejected.
  The router is the facade.

### 2. Screens and the routes that fill them

| Screen | Route | Reads | Writes |
|--------|-------|-------|--------|
| Welcome | before the shell | — | `POST /api/auth/signup`, `POST /api/auth/signin` |
| Home | `/` | none | none |
| Brain | `/brain` | `GET /api/chats`, `GET /api/chats/{id}/turns` | `POST /api/chats`, `POST /api/chat` |
| Brain calendar | `/brain`, premium | `GET /api/calendar` | `PUT /api/calendar/{day}` |
| Memory | `/memory` | `GET /api/documents`, `GET /api/documents/search` | `POST /api/upload` |
| Decisions | `/decisions` | `GET /api/simulations` | `POST /api/simulate` |
| Analytics | `/analytics` | `GET /api/analytics/correlations`, `GET /api/analytics/metrics` | `POST /api/analytics/ingest` |
| Shield | `/shield` | `GET /api/shield/incidents` | `POST /api/shield/scan` |
| Learning | `/learning` | `GET /api/learning` | `POST /api/finetune` |
| Settings | `/settings` | `GET /api/account`, `GET /api/status`, `GET /api/storage` | `PATCH /api/account`, `DELETE /api/data` |

Home is a map of the six product screens. It does not call the API.
Clicking Encefalus returns to Home. Settings is available on both plans.
Log out clears the session and returns to welcome.

`GET /api/analytics/insights`, `GET /api/shield/guidelines`, and
`GET /api/simulations/{id}` exist. The screens do not call them. The
narrative arrives with correlations. A past decision arrives whole in
the simulations list. A shield scan returns the evidence the detail
panel shows, and the incidents list includes that evidence too.

### 3. Free and Premium

**Decision**: Sign-up sends `plan: "free"`. The shell reads `plan` from
the account stored with the token.

- Free Brain sets `use_rag` false. Up to five files may be attached to
  one question. Their text stays on that chat and is sent again with
  later questions in the same chat. It is not written to documents,
  GridFS, or RAG. Calendar notes are not loaded.
- Memory, Decisions, Analytics, Shield, and Learning render a premium
  notice on the free plan and do not present that module's data.
- The router enforces the same split: those modules respond 403 for a
  free token. Brain chat, the chat list, and turns stay open.

**Alternatives considered**:
- Hide the premium links — rejected. Home and the sidebar still list
  every module. The screen itself explains the plan.
- Block the whole web app for free — rejected. Free includes Brain.

### 4. Analytics screen does not compute the correlation

**Decision**: The Analytics screen draws two scatters from
`points` on `sleep_productivity` and `meetings_focus`. It prints `r`
and `n` from the payload. `status: "insufficient"` shows an English
empty state and no invented `r`. The narrative in the reading panel is
the string the API returned.

The anteproyecto names Chart.js. The delivered screen is a React
scatter bound to that JSON. Recharts is in the app dependencies. This
screen does not use it, and it does not use Chart.js. The contract is
`points`, `r`, `n`, and `narrative`.

Ingest accepts `.csv`, `.xlsx`, `.docx`, `.ics`, and an image, then
reloads correlations and metrics.

### 5. Analytics Service behind that screen

**Decision**: `POST /ingest` on port 8008 accepts those file types.
LangChain loaders turn a file into text. An image is OCR'd, and the
model also receives the image bytes. One `POST /chat` to Qwen3.5-4B
(temperature 0) receives that text, the image when present, and RAG
context for that `user_id`. It returns JSON days and an English
`narrative`. Hours outside 0–24 or a score outside 1–10 are dropped
for that field. Empty or unreadable files are 422. LLM failure is
502/504 and no write.

Pearson, after the days exist:

```
r = Σ(x-x̄)(y-ȳ) / sqrt(Σ(x-x̄)² Σ(y-ȳ)²)
```

`n < 2` or zero variance → `r: null`, `status: "insufficient"`. `r` is
rounded to 4 decimals. No p-values, no Monte Carlo.

`life_metrics` is unique on `(user_id, date)`. A successful ingest
writes `analytics_snapshots` with both pairs, the narrative,
`inferred_facts`, and `llm_used: true`.

### 6. MCP without changing chat graphs

**Decision**: `analytics_query` calls Analytics `GET /correlations`.
`reason_graph` is unchanged. The web app never calls
`POST /mcp/tools/analytics_query`.

### 7. Settings

**Decision**: Six rows from `GET /api/status`: LLM core, Memory
retrieval, Personal model (fine-tune), Analytics, Agents, Shield.
Storage is the byte size of that user's uploaded documents
(`GET /api/storage`). Plan is only free or premium (`PATCH /api/account`).
Delete all data removes that user's uploads and the RAG memory
(`DELETE /api/data`). There is no member-since, no privacy-controls
card, no inference-location card, and no export card.

## Data Flow

### Sign in

```
1. Welcome POST /api/auth/signup or /api/auth/signin
2. Router returns access_token and user (id, name, email, plan)
3. sessionStorage holds both. The shell opens.
4. Log out clears both and the welcome screen returns.
```

### A product screen

```
1. Shell checks the plan.
2. Free on Memory, Decisions, Analytics, Shield, or Learning
   → premium notice. No module data is shown.
3. Otherwise the screen GET or POSTs /api/... with the bearer token.
4. Router checks JWT, plan, and rate limit, then calls the service.
5. The screen renders that JSON. It does not recompute it.
```

### Analytics ingest

```
1. Analytics screen POST /api/analytics/ingest (file)
2. Router: JWT, premium, 10/min, X-Request-ID
3. Router POST analytics-service:8008/ingest
4. Load the file. RAG search. LLM POST /chat (temperature 0)
5. Upsert life_metrics. Pearson. Write analytics_snapshots.
6. 200 {rows_upserted, correlations, insights, llm_used}
7. The screen reloads correlations and metrics and redraws.
```

### MCP (not used by the browser)

```
POST agents:8006/mcp/tools/analytics_query
  → GET analytics:8008/correlations (same X-Request-ID)
```

### Errors

```
No JWT                         → welcome screen
Free on a premium screen       → premium notice; router would 403
Unreadable analytics file      → 422, no write, no LLM
LLM 5xx / bad JSON             → 502/504, no write
11th ingest in a minute        → 429
31st correlations read/minute  → 429
Cross-user id                  → 404
Analytics down                 → the screen shows the router error
```

## Configuration

```
ANALYTICS_HOST=0.0.0.0
ANALYTICS_PORT=8008
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://host.docker.internal:8003
LLM_TEMPERATURE=0
MONGODB_URI=...
MONGODB_DB=llm_brain
```

Router and Agents: `ANALYTICS_SERVICE_URL=http://analytics-service:8008`.
Rate limits: `RATE_LIMIT_ANALYTICS_INGEST=10`,
`RATE_LIMIT_ANALYTICS_QUERY=30`.

Web: same-origin `/api`. Vite dev proxy targets `http://localhost:8000`.
Compose `web` listens on host port 5173 and proxies `/api` to
`http://api-router:8000`.

## Data model (MongoDB)

Chat turns, documents, simulations, incidents, and accounts stay in the
collections their own frames own. This frame adds:

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

The browser stores only `access_token` and the account
`{id, name, email, plan}` in `sessionStorage`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| A screen and its route drift | The screen reads the fields the route returns; tests cover the pairs the UI renders |
| Free user opens a premium URL | The screen shows the premium notice; the router returns 403 |
| Tiny n makes r noisy | `insufficient` when n < 2; the scatter does not invent r |
| Anteproyecto says Chart.js | The scatter is React bound to `points`, `r`, `n`; the math stays on the server |
| LLM JSON is malformed | One retry, then 502 and no write |
| JWT in the browser | sessionStorage; HTTPS is future |
| Welcome is outside the shell | No product fetch runs until a token exists |

## Migration Plan

1. Deploy Analytics Service via Docker Compose.
2. Add the router analytics routes and the Agents tool.
3. Serve `apps/web` against the local router (Vite, or nginx profile `web`).
4. Rollback: stop `web` and `analytics-service`. Chat, simulate, and
   shield keep working through the router.

## Open Questions

None that block the specs. Pomodoro timers in the anteproyecto alcance
are not in the Frame 7 description. They stay out.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Facade** | API Router | The browser never addresses a service port |
| **Gate** | Welcome vs shell; premium notice | No session stays on welcome; free stays out of premium data |
| **BFF-less SPA** | `apps/web` | Same-origin `/api` only |
| **Protocol (MCP tools)** | `analytics_query` | Agents can read correlations; the UI does not |
| **Repository** | `life_metrics` / snapshots | Per-user analytics persistence |
| **DTO / snapshot** | `analytics_snapshots` | The `r` the screen shows is the `r` that was stored |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Each screen renders one module. Loader, LLM client, and Pearson stay in Analytics Service |
| **O** | A new sidebar entry is a route plus a screen. A new correlation pair still uses `points`, `r`, `n` |
| **L** | CSV, XLSX, DOCX, ICS, and an image all become text the same ingest path can score |
| **I** | The screen calls the route it renders. It does not take the MCP interface |
| **D** | Screens depend on router JSON. Analytics depends on RAG and LLM URLs |
