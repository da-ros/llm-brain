## Why

The product had services and no place to use them. Frame 7 is the Encefalus
**user interface**: the first screen a person sees, then Home, then one
screen for each module already built. The anteproyecto calls objetivo 7
Life Analytics. That dashboard is the **Analytics** screen inside this
interface. The rest of the frame is the shell that signs a person in and
shows Brain, Memory, Decisions, Shield, Learning, and Settings from the
API Router.

Every screen that shows product data is built from a router response.
The browser does not call a service port, does not compute Pearson, and
does not run the decision tree.

## Context from Frame 6 and Frame 8

- **Frame 6 (Simulator, port 8007)**: what-if runs stay in `simulations`.
  The Decisions screen lists them with `GET /api/simulations` and starts
  a run with `POST /api/simulate`. Frame 7 does not change the tree.
- **Frame 8 (Privacy & Scam Shield)**: the Shield screen lists incidents
  with `GET /api/shield/incidents` and scans with `POST /api/shield/scan`.
  The list shape is `{ incidents: [{ id, created_at, severity, summary, source, rationale, reasons }] }`.
- **Frame 1.1**: JWT, CORS, and the router facade. Clients talk only to
  port 8000.
- **Frame 3**: Memory lists and searches documents through the router.
  The web app does not embed Chroma.
- **Frame 4 and Frame 5**: Brain chat and the Learning screen use the
  router. Learning reads `GET /api/learning` and starts a ready batch
  with `POST /api/finetune`. The browser does not call Agents or
  Fine-Tune.
- **OAuth federado is out of scope.** Sign-up is name, email, and
  password. There is no Continue with Apple or Google. A diary or
  schedule on Analytics is a file upload, not a live calendar connection.

## What Changes

- Add the web app in `apps/web/` (React, English). A person with no
  session sees the welcome screen and can sign up or sign in. A session
  opens the product shell.
- Home is `/`. The mark and the word Encefalus return there. The sidebar
  opens Brain, Memory, Decisions, Analytics, Shield, and Learning.
  Settings sits under those.
- **Free** can use Brain (chat list, turns, and chat, including up to
  five files on a question) and Settings. Memory, Decisions, Analytics,
  Shield, and Learning show that those screens are on the Premium plan.
  A free chat does not use RAG and does not store uploads as memory.
- **Premium** uses every screen. Brain can use memory and calendar
  notes. Analytics plots two correlations from the API and can ingest a
  diary or schedule file.
- Add **Analytics Service** (`services/analytics/`, port **8008**) for
  that screen: ingest CSV, XLSX, DOCX, ICS, or an image; infer days with
  Qwen3.5-4B; compute Pearson for sleep vs productivity and meetings vs
  focus; persist the points and the narrative. The screen only draws
  the returned points and shows `r`, `n`, and the narrative.
- Register MCP tool **`analytics_query`** on Agents. The web app does
  not call it. `reason_graph` is not rewritten.
- API Router remains the only client entry. This frame adds the premium
  analytics routes. The other screens use routes the earlier frames
  already expose, plus account, chat, and chat-list routes the shell
  needs.
- Dev proxy and the Compose nginx service forward `/api` to the router.
- Out of scope: Google OAuth, multilingual UI, Apple or Google sign-in,
  Monte Carlo, live calendar sync, the mobile app (Frame 10), and
  `POST /api/sessions/end`.

## Capabilities

### New Capabilities
- `user-interface`: Encefalus web app. Welcome, Home, and the product
  screens. Each data screen is filled from the API Router. Free is
  Brain plus Settings. Premium is the full product. Analytics draws two
  correlations and does not compute them.
- `analytics-service`: CSV/XLSX/DOCX/ICS/image ingest, LLM inference,
  two Pearson correlations, per-user persistence. This is the backend
  of the Analytics screen.

### Modified Capabilities
- `agents-service`: register MCP tool `analytics_query`. The UI does
  not call MCP.
- `api-router`: premium analytics routes, and the browser is limited
  to the router.

## Output

```
openspec/changes/objective-7-user-interface/
├── output/
│   ├── diagrams/
│   │   ├── ui-architecture.drawio
│   │   ├── ui-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── user-interface/spec.md
    ├── analytics-service/spec.md
    ├── agents-service/spec.md
    └── api-router/spec.md
```

## Impact

- New UI: `apps/web/`. Welcome outside the product. Shell, Home, and
  eight routes inside it.
- New service: `services/analytics/` (FastAPI, port 8008), used by the
  Analytics screen through the router.
- MongoDB collections `life_metrics` and `analytics_snapshots` for that
  screen. Chat turns, documents, simulations, and incidents stay in the
  collections their own frames own.
- API Router: `ANALYTICS_SERVICE_URL` and the analytics routes. The web
  app also calls account, chat, documents, calendar, simulate, shield,
  learning, and finetune routes that already sit on the router.
- Agents Service: one extra MCP tool. Graphs unchanged. The browser
  never uses it.
- Docker Compose: `analytics-service` on 8008. Optional `web` nginx on
  5173, profile `web`, proxying `/api` to the router.
- Kafka is unchanged. No Google OAuth.

## Execution Order

1. Web shell: welcome, session, Home, sidebar.
2. Wire each product screen to the router response it displays.
3. Free and Premium gates on the screens that are not Brain or Settings.
4. Analytics Service (ingest, Pearson, persistence) and the Analytics
   screen that plots it.
5. MCP `analytics_query` and the router analytics routes.
6. Tests for the service, the router, and the screen contracts.
7. `output/` diagrams and justificacion.
