## 1. Analytics Service foundation

- [ ] 1.1 Create `services/analytics/` package (`__init__.py`, `main.py` FastAPI app, unauthenticated `GET /health` returning `service: analytics-service`)
- [ ] 1.2 Add `services/analytics/config.py` (pydantic-settings: port 8008, MongoDB, RAG URL, LLM URL, temperature 0) and pin versions in `services/analytics/requirements.txt`
- [ ] 1.3 Add correlation ID middleware and structured logging (`CorrelationFilter`, `X-Request-ID` generate-if-missing)
- [ ] 1.4 Add `services/analytics/Dockerfile`; register `analytics-service` on port 8008 in Docker Compose with `RAG_SERVICE_URL` and `LLM_SERVICE_URL`

## 2. Ingest, LLM inference, Pearson, and persistence

- [ ] 2.1 Load CSV, XLSX, DOCX, ICS, and images (PNG/JPEG/WEBP) with LangChain document loaders; OCR images via the image loader; 422 on empty or unsupported types; no Google OAuth
- [ ] 2.2 Call LLM Service `POST /chat` (temperature 0, `X-Request-ID`) with the loaded text, the image bytes when the upload is a photo, and RAG excerpts for that `user_id`; parse JSON days plus `narrative` and `inferred_facts`; retry once on invalid JSON; 502/504 and no write if the model fails
- [ ] 2.3 Upsert `life_metrics` on unique `(user_id, date)` with the inferred fields; drop hours outside 0–24 and scores outside 1–10 per field
- [ ] 2.4 Implement pairwise-complete Pearson r (4 decimal places) on the inferred series; `n < 2` or zero variance → `r: null`, `status: insufficient`; no Monte Carlo
- [ ] 2.5 Write `analytics_snapshots` (`llm_used`, narrative, both pairs) after each successful ingest; expose `POST /ingest`, `GET /correlations`, `GET /insights`, `GET /metrics` with `user_id` isolation and 404 cross-user; 403 free

## 3. MCP tool and API Router

- [ ] 3.1 Register Agents MCP tool `analytics_query` wrapping Analytics `GET /correlations`; `GET /mcp/tools` lists it; unknown tool still 404; do not change `reason_graph` / `learn_graph`
- [ ] 3.2 Add Router `ANALYTICS_SERVICE_URL` and `POST /api/analytics/ingest` (premium JWT, 10 req/min, 401/403/422/429, no Kafka); forward `X-Request-ID`
- [ ] 3.3 Add Router `GET /api/analytics/correlations` (30 req/min), `GET /api/analytics/insights`, and `GET /api/analytics/metrics` (premium, 403 free, 404 cross-user)

## 4. React + Chart.js dashboard

- [ ] 4.1 Scaffold `apps/web/` Vite + React (English UI); login against Router JWT; persist token in `sessionStorage`; reject free-tier tokens with a premium-only message
- [ ] 4.2 Build two interactive Chart.js scatter charts from `GET /api/analytics/correlations` (sleep vs productivity, meetings vs focus); show `r` and `n`; insufficient pair shows English empty copy, not a fake r; show the LLM `narrative` in an insights panel
- [ ] 4.3 Add file upload for `.csv`, `.xlsx`, `.docx`, `.ics`, and images calling `POST /api/analytics/ingest` then refresh charts and insights
- [ ] 4.4 Add simulations panel (`GET /api/simulations`) and Shield incidents panel (`GET /api/shield/incidents`) with empty/unavailable state on 404/501/network error
- [ ] 4.5 Dev proxy `/api` → Router `:8000`; optional Compose nginx service for `apps/web/dist`

## 5. Tests

- [ ] 5.1 Unit tests: Pearson fixture (known r), insufficient n, csv/xlsx/docx/ics/image load with OCR on images, LLM client invoked on success, LLM 5xx does not write, 422 on empty file
- [ ] 5.2 Unit tests: upsert isolation, free 403, cross-user 404, MCP `analytics_query` listed
- [ ] 5.3 Integration tests: Router ingest → correlations 200 (mocked DB); rate limits 429; Shield-missing dashboard path does not fail analytics
- [ ] 5.4 Web component/tests or RTL: premium charts render points; insufficient label; incidents empty state

## 6. Documentation (output/)

- [ ] 6.1 Create `output/diagrams/analytics-architecture.drawio` (existing Frame 1.1/6 services in blue, Analytics + web in green; Shield contract in yellow)
- [ ] 6.2 Create `output/diagrams/analytics-dataflow.drawio` (load → RAG + LLM → Pearson → snapshot → charts and insights; simulations list; Shield degrade; MCP; no OAuth/Kafka)
- [ ] 6.3 Create `output/diagrams/README.md` with arrow legend and colour scheme
- [ ] 6.4 Create `output/documents/justificacion-ejemplo.md` with LLM inference plus Pearson vs Monte Carlo, file types vs OAuth, SOLID/patterns, and structured-log examples for `/ingest`, LLM `POST /chat`, `/correlations`, MCP `analytics_query`, and CorrelationFilter
