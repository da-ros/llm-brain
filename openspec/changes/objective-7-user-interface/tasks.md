## 1. Web shell

- [x] 1.1 Scaffold `apps/web/` (React, English). Welcome is the first screen when there is no session. Sign up with name, email, and password (`POST /api/auth/signup`, plan free) and sign in (`POST /api/auth/signin`). Store the token and the account in `sessionStorage`. No Apple or Google button.
- [x] 1.2 Home at `/` with the six product cards and no extra tabs. The Encefalus mark returns to Home. The sidebar opens Brain, Memory, Decisions, Analytics, Shield, Learning, and Settings.
- [x] 1.3 Dev proxy `/api` → Router `:8000`. Compose nginx service `web` (profile `web`, host port 5173) proxies `/api` to `api-router:8000`.

## 2. Product screens

- [x] 2.1 Brain: list chats, reload turns when a chat opens, send `POST /api/chat` with the chat id. Up to five files on a question. Premium may load and save calendar notes. Free sends `use_rag` false and does not show the calendar.
- [x] 2.2 Memory: list and search `GET /api/documents`, upload with `POST /api/upload`. Free sees the premium notice.
- [x] 2.3 Decisions: list past runs with `GET /api/simulations` and run `POST /api/simulate`. Opening a run restores the question, scenarios, assumptions, and sources. Free sees the premium notice.
- [x] 2.4 Analytics: two scatters from `GET /api/analytics/correlations` (sleep vs productivity, meetings vs focus), showing `r` and `n` from the payload. Insufficient data is an English empty state, not a fake `r`. The reading panel shows the API `narrative`. The days table uses `GET /api/analytics/metrics`. Ingest accepts `.csv`, `.xlsx`, `.docx`, `.ics`, and an image via `POST /api/analytics/ingest`, then refreshes. Free sees the premium notice.
- [x] 2.5 Shield: list `GET /api/shield/incidents` and scan with `POST /api/shield/scan`. The detail shows the returned rationale and reasons. Free sees the premium notice.
- [x] 2.6 Learning: load `GET /api/learning`. Fine-tune posts `{batch_id}` to `POST /api/finetune` when the batch is ready. Free sees the premium notice.
- [x] 2.7 Settings: account, six service rows, and storage from `GET /api/account`, `GET /api/status`, and `GET /api/storage`. Plan patch uses `PATCH /api/account`. Delete all data uses `DELETE /api/data`. Log out clears the session. Settings stays available on the free plan.

## 3. Analytics Service

- [x] 3.1 Create `services/analytics/` (`GET /health` → `service: analytics-service`), config (port 8008, MongoDB, RAG URL, LLM URL, temperature 0), correlation ID middleware, Dockerfile, and Compose service `analytics-service`.
- [x] 3.2 Load CSV, XLSX, DOCX, ICS, and images with LangChain loaders. OCR an image. Call LLM `POST /chat` with the text, the image when present, and that user's RAG excerpts. Retry once on invalid JSON. 502/504 and no write if the model fails. 422 on an empty or unsupported file. No Google OAuth.
- [x] 3.3 Upsert `life_metrics` on `(user_id, date)`. Pearson r to 4 decimals on the two pairs. `n < 2` or zero variance → `r: null`, `status: insufficient`. Write `analytics_snapshots` after a successful ingest. Expose `POST /ingest`, `GET /correlations`, `GET /insights`, `GET /metrics` with `user_id` isolation. 403 for free. 404 cross-user.

## 4. MCP tool and API Router

- [x] 4.1 Register Agents MCP tool `analytics_query` wrapping Analytics `GET /correlations`. Do not change `reason_graph` / `learn_graph`. The web app does not call this tool.
- [x] 4.2 Router `ANALYTICS_SERVICE_URL`, `POST /api/analytics/ingest` (premium, 10/min, 401/403/422/429, no Kafka), and `GET /api/analytics/correlations` (30/min), `GET /api/analytics/insights`, `GET /api/analytics/metrics` (premium, 403 free, 404 cross-user). Forward `X-Request-ID`.

## 5. Tests

- [x] 5.1 Analytics unit tests: known Pearson r, insufficient n, csv/xlsx/docx/ics/image load, LLM called on success, LLM 5xx does not write, 422 on an empty file.
- [x] 5.2 Analytics and router tests: user isolation, free 403, cross-user 404, MCP `analytics_query` listed.
- [x] 5.3 Router ingest → correlations 200 with the DB mocked. Rate limits return 429.
- [x] 5.4 The web screens call the routes in the table in `design.md`. A free account is sent to the premium notice on Memory, Decisions, Analytics, Shield, and Learning. The Analytics scatter does not invent `r`.

## F. Documentation (output/)

- [x] 6.1 Create `output/diagrams/ui-architecture.drawio` (Encefalus web in green, existing services in blue, Analytics in green, Shield in yellow). The browser's only edge is to the API Router.
- [x] 6.2 Create `output/diagrams/ui-dataflow.drawio` (welcome → session → screen → router → service → screen). Include the analytics ingest branch and the free-plan notice. No OAuth. No Kafka on this path.
- [x] 6.3 Create `output/diagrams/README.md` with the arrow legend and the colour scheme.
- [x] 6.4 Create `output/documents/justificacion-ejemplo.md` for the user interface: one facade, free vs premium, the Analytics screen versus Pearson, and structured-log examples for a screen call and for `/ingest`.
