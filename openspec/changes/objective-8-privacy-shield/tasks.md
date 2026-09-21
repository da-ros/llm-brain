## 1. RAG embed and Shield foundation

- [ ] 1.1 Add RAG `POST /embed` for `modality` text, image, or video (2048-dim `vector`, 422 if the payload is empty, no Chroma write, propagate `X-Request-ID`)
- [ ] 1.2 Fill `services/shield/` package (`__init__.py`, `main.py` FastAPI app, unauthenticated `GET /health` returning `service: shield-service`)
- [ ] 1.3 Add `services/shield/config.py` (port 8009, RAG URL, LLM URL, temperature 0, MongoDB, `SIMILARITY_THRESHOLD=0.80`, `MAX_UPLOAD_BYTES`, `CORPUS_PATH`) and pin versions in `services/shield/requirements.txt`
- [ ] 1.4 Add correlation ID middleware and structured logging; `Dockerfile`; register `shield-service` on port 8009 in Docker Compose with `RAG_SERVICE_URL` and `LLM_SERVICE_URL`

## 2. Heuristics, embeddings, and LLM verdict

- [ ] 2.1 Author `data/shield/corpus.jsonl` with 30 labeled samples (~20 phishing/scam, ~10 ham; sources email/sms/message)
- [ ] 2.2 OCR images with the LangChain image loader before heuristics; run the heuristic pack (`urgency`, `credential`, `money`, `short_url`, `lookalike_host`, `prize`) on pasted text and on OCR text; record `ocr_empty` when an image yields no text; do not OCR video; heuristics are evidence, not the verdict
- [ ] 2.3 At startup embed the text corpus via RAG `POST /embed` and cache vectors; on scan embed the submitted text, image, or video and cosine against that gallery
- [ ] 2.4 Call LLM Service `POST /chat` (temperature 0, `X-Request-ID`) with pasted text, OCR text, and/or media plus heuristic ids and nearest-neighbour score; parse JSON `likelihood`, `alert`, `severity`, `summary`, `rationale`; the model's `alert` is the verdict; retry once on invalid JSON; 502/504 and no persist if the model fails; if embed fails, still call the LLM with reason `embedding_unavailable`

## 3. Persistence and HTTP API

- [ ] 3.1 Create MongoDB `shield_incidents` with unique `correlation_id` and `user_id` index; persist only when `alert` is true; idempotent retry returns stored result
- [ ] 3.2 Expose `POST /scan` for text and/or image/video (422 when both are missing, source is invalid, or the file exceeds 20 MB; 403 free), `GET /incidents` as `{incidents: [{id, created_at, severity, summary, source}]}` (200 even if empty, 404 cross-user), and `GET /guidelines` English responsible-use text that mentions multimodal LLM reasoning
- [ ] 3.3 Include `reasons[]` on every 200 scan (heuristic ids, nearest corpus id + score when embed succeeded, and an `llm` rationale)

## 4. MCP, Router, and web popup

- [ ] 4.1 Register Agents MCP tool `scan_message` wrapping Shield `POST /scan`; `GET /mcp/tools` lists it; unknown tool still 404; do not change `reason_graph` / `learn_graph`
- [ ] 4.2 Add Router `SHIELD_SERVICE_URL`, `POST /api/shield/scan` (premium JWT, 30 req/min, 401/403/429, no Kafka), `GET /api/shield/incidents`, and `GET /api/shield/guidelines`
- [ ] 4.3 Add English scan form (textarea, source, image/video file input) and threat popup on `alert` true showing likelihood and reasons in `apps/web` (minimal `/shield` page if Frame 7 dashboard is absent); refresh incidents list; premium-only copy for free tokens

## 5. Tests

- [ ] 5.1 Unit tests: text, image, and video scans call the LLM once; an image scan OCRs before heuristics; a video scan does not OCR; `alert` follows the model; ham with `alert` false does not persist; 422 when text and file are both missing
- [ ] 5.2 Unit tests: embed 5xx still calls the LLM with `embedding_unavailable`; LLM 5xx does not persist; idempotent `correlation_id`; free 403; cross-user 404
- [ ] 5.3 Unit tests: RAG `POST /embed` length 2048 for text, image, and video and no collection growth; MCP `scan_message` listed; unknown tool 404
- [ ] 5.4 Integration tests: Router premium scan → 200 + incidents list Frame 7 shape; rate limit 429; guidelines 200

## 6. Documentation (output/)

- [ ] 6.1 Create `output/diagrams/shield-architecture.drawio` (existing Frame 1.1/3/5 in blue, Shield in green, RAG `/embed` in yellow)
- [ ] 6.2 Create `output/diagrams/shield-dataflow.drawio` (image OCR → heuristics → embed → LLM `/chat` → persist; video skips OCR; popup; MCP; LLM 5xx; free 403; no Kafka)
- [ ] 6.3 Create `output/diagrams/README.md` with arrow legend and colour scheme
- [ ] 6.4 Create `output/documents/justificacion-ejemplo.md` with LLM verdict vs supervised models, multimodal `/embed` vs Chroma access, SOLID/patterns, Frame 7 contract, and structured-log examples for `/scan`, RAG `/embed`, LLM `POST /chat`, `/incidents`, MCP `scan_message`, and CorrelationFilter
