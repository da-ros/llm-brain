## Why

The anteproyecto lists external threats as a first-class job of the Digital
Brain: users already store mail, SMS, images, and clips, but nothing flags
phishing or scam before they act. Frame 8 adds the **Privacy & Scam
Shield**. Heuristics and embedding similarity still gather evidence.
**Qwen3.5-4B** (multimodal: text, image, and video) reasons over that
evidence and states the likelihood the item is a scam. The UI shows a
**popup** and persists **incidents**. A supervised fraud model and voice
impersonation stay out of scope.

## Context from Frame 1.1 and Frame 3

- **Frame 1.1 (API Router, port 8000)**: JWT, `X-Request-ID`, premium/free
  gating, Router as facade. Clients never address backend ports.
- **Frame 3 (RAG, port 8002)**: Qwen3-VL-Embedding-2B (2048-dim) embeds
  text, image, and video. Shield **must not** open Chroma. Frame 8 adds
  `POST /embed` (`modality` text|image|video, 2048-dim vector, nothing
  stored) so Shield can cosine-compare against a labeled scam corpus.
- **Frame 4 (LLM, port 8003)**: Qwen3.5-4B base is natively multimodal.
  Shield calls `POST /chat` (temperature 0) with the text and/or the
  image or video bytes plus the heuristic and similarity evidence. The
  model returns likelihood, alert, severity, summary, and rationale.
  Shield does not load weights. LLM failure is 502/504 and no incident.
- **Frame 6** is **parallel** (`context.txt`: 6 ∥ 8). Shield does not
  call the simulator.
- **Frame 7** already specified the incidents contract this frame MUST
  honour so the dashboard panel lights up:
  `GET /api/shield/incidents` →
  `{ incidents: [{ id, created_at, severity, summary, source }] }`.
  Frame 7 may apply later; until then the API still returns 200 with an
  empty list. Frame 8 also adds a scan form + popup on the web app
  (placeholder today; full dashboard in Frame 7).

Free tier has no files and no cloud RAG, so Shield is **premium-only**.
OAuth mailbox connectors, live SMS intercept, and full-scale classifiers
are out of scope. Input is a pasted email/SMS/message, an image, or a
short video (~30 text fixtures in-repo, plus image/video samples),
matching the thesis cronograma and the multimodal model.

## What Changes

- Add **Shield Service** (`services/shield/`, port **8009**) that:
  - Accepts pasted text (`source` email|sms|message) **and/or** an image
    or a short video
  - **OCRs every image** with the LangChain image loader before any
    heuristic. A screenshot is treated as a message: heuristics and the
    text embedding run on the OCR string. The image bytes still go to the
    LLM. Video is not OCR’d
  - Runs a **deterministic heuristic pack** on pasted text and on OCR
    text (urgency,
    credential harvest, money/gift-card/crypto, short URLs, lookalike
    hosts, prize/lottery)
  - Embeds the text, image, or video via RAG `POST /embed` and
    cosine-compares against a **30-item labeled corpus**
  - Calls **Qwen3.5-4B** with that evidence. The model decides
    `likelihood` (0–1), `alert`, `severity`, `summary`, and `rationale`.
    Heuristics alone do not raise an alert
  - Returns an **explainability** payload (`reasons[]`: heuristic ids,
    nearest corpus id + score, and the LLM rationale)
  - Persists **alert** rows in MongoDB `shield_incidents` when the LLM
    sets `alert` true
- Add RAG **`POST /embed`** for text, image, and video (2048-dim; no
  persist).
- Register MCP tool **`scan_message`** on Agents Service wrapping Shield
  HTTP. `reason_graph` is **not** rewritten.
- API Router (premium only):
  - `POST /api/shield/scan` → HTTP sync → **200** (alert + reasons;
    **not** Kafka)
  - `GET /api/shield/incidents` → Frame 7 contract
  - `GET /api/shield/guidelines` → static English responsible-use text
- Rate limit scan at **30 req/min**. Correlation ID on every hop.
- Web: English scan form (paste text and/or attach an image or video) +
  **popup** when `alert` is true; incidents list uses the same GET.
  Works as a minimal page if Frame 7 dashboard is not built yet.
- Docker Compose: `shield-service` on 8009.
- Out of scope: supervised fraud models, voice deepfakes, live SMS
  gateway, Free-tier Shield, OAuth inbox sync, Monte Carlo.

## Capabilities

### New Capabilities
- `shield-service`: multimodal scan (text, image, video), heuristics and
  embedding evidence, LLM scam likelihood, incident persistence,
  explainability, responsible-use guidelines, premium-only HTTP API.

### Modified Capabilities
- `hybrid-store-rag`: add `POST /embed` for text, image, and video query
  vectors (no storage).
- `agents-service`: register MCP tool `scan_message` wrapping Shield HTTP.
- `api-router`: premium scan / incidents / guidelines routes; 401/403/429.
- `life-analytics-web`: scan form, popup alert, incidents list bound to
  the Frame 7 contract (empty list is valid).

## Output

```
openspec/changes/objective-8-privacy-shield/
├── output/
│   ├── diagrams/
│   │   ├── shield-architecture.drawio
│   │   ├── shield-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── shield-service/spec.md
    ├── hybrid-store-rag/spec.md
    ├── agents-service/spec.md
    ├── api-router/spec.md
    └── life-analytics-web/spec.md
```

## Impact

- New service: `services/shield/` (FastAPI, Dockerfile, port 8009).
  Placeholder package already exists from Frame 1; this frame fills it.
- New MongoDB collection `shield_incidents`.
- New fixture corpus `data/shield/corpus.jsonl` (30 labeled samples).
- RAG: `POST /embed` only; Chroma schema unchanged.
- API Router: shield routes + `SHIELD_SERVICE_URL`.
- Agents Service: one extra MCP tool; graphs unchanged.
- Web: scan UI + popup; Frame 7 incidents panel becomes live.
- Kafka: **unchanged**.
- Downstream: Frame 7 `GET /api/shield/incidents` returns 200.
- Out of scope: AWS, Free tier, supervised models, voice.

## Execution Order

1. RAG `POST /embed` (text/image/video) + Shield Service skeleton.
2. Heuristic pack + corpus cosine, then LLM `POST /chat` for the verdict.
3. Persist alerts; scan / incidents / guidelines HTTP.
4. MCP `scan_message`; API Router premium routes + rate limit.
5. Web scan form + popup + incidents list.
6. Tests (30-fixture corpus, heuristic/embedding paths, 403/404).
7. `output/` diagrams and justificacion with structured-log examples.
