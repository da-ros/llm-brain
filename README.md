# llm-brain — AI-Augmented Digital Brain

> MSc Software thesis MVP: a **multi-tenant** personal LLM/OS emulating a **Brain–LLM symbiosis**
> for infinite human memory, personal knowledge management (PKM), advanced reasoning and
> decision-making support.

**Authors:** Pedro David Rodas Mantilla · Giovanny Daniel Jácome Cajamarca
**Tutor:** Ing. Rodolfo Bojorque, PhD · **Institution:** UPS
**Research line:** Sistemas Informáticos e Inteligencia Artificial en Ciencia de Datos

## What it does

Integrates PKM with fine-tuned LLMs, RAG, agentic AI coordinated via **MCP**, and explainable
prompt engineering to help a user **remember, reason, and decide** over their personal data.

Local MVP only: the "cloud" LLM is a **Docker container** serving **Qwen3.5-4B base**.
AWS (Bedrock, ECS, API Gateway) is future work.

## Modules (mapped to the thesis objectives)

| # | Module | Path |
|---|--------|------|
| 1 | Architecture & repo (C4, MCP, CI, JWT, LLM protocol) | `apps/api/`, `docs/architecture/` |
| 2 | One-Tap Memory Distillation (ETL → JSON triples) | `services/etl/` |
| 3 | Hybrid store + RAG (Mongo + Chroma + LangChain) | `services/rag/` |
| 4 | LLM container (Qwen3.5-4B base) + local LoRA | `services/llm/`, `services/finetune/` |
| 5 | Symbiotic Learning Loop (MCP: Ingestor/Razonador/Evaluador) | `services/agents/` |
| 6 | Decision-Support Simulator (what-if) | `services/simulator/` |
| 7 | Life Analytics (React + Chart.js) | `apps/web/` |
| 8 | Privacy & Scam Shield | `services/shield/` |
| 9 | Alpha validation & KPIs | across modules + `apps/api/` |

## Repository layout

```text
llm-brain/
├─ openspec/       # Spec-driven development: specs (truth) + changes (proposals)
├─ apps/
│  ├─ api/         # Platform foundation (health, JWT, LLMProvider)
│  └─ web/         # React + Chart.js dashboard (later frame)
├─ services/
│  ├─ api-router/  # Gateway (JWT, Kafka, routing) — Frame 1.1
│  ├─ etl/         # One-Tap Memory Distillation
│  ├─ rag/         # LangChain + Chroma
│  ├─ llm/         # Qwen3.5-4B base container (port 8003)
│  ├─ finetune/    # Local LoRA → Premium on-device
│  ├─ agents/      # MCP Ingestor / Razonador / Evaluador
│  ├─ simulator/   # Decision-Support Simulator
│  └─ shield/      # Privacy & Scam Shield
├─ notebooks/      # Fine-tune experiment log
├─ infra/          # Pointers to Docker Compose / Dockerfile
└─ docs/architecture/  # C4, stack, security, decisions
```

## Spec-driven development (OpenSpec)

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) to align on specs before
code. Each module is an OpenSpec **change** (`proposal → specs → design → tasks`) that is
archived into `openspec/specs/` once implemented — building a traceable record for the defense.

```bash
openspec list            # active changes
openspec show <change>   # view a change
openspec validate        # validate spec formatting
```

In Cursor, drive the workflow with slash commands: `/opsx-propose`, `/opsx-apply`, `/opsx-archive`.

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # JWT_SECRET_KEY is required
uvicorn apps.api.main:app --reload --port 8000
```

Local stack (MongoDB, Chroma, Kafka, services):

```bash
docker compose up --build
# Frame 1 foundation API only:
docker compose --profile foundation up --build api mongo chroma
```

### Memory distillation (Frame 2)

`POST /api/upload` on the API Router (port 8000) is async: JWT + python-magic MIME + 10MB
limit → GridFS → Kafka `file.uploaded` → **202**. The ETL Service (port 8001) loads the
file with LangChain document loaders, calls the LLM Service (`POST /extract`, base
Qwen3.5-4B) for triples, and writes `data/triples/{user_id}/{correlation_id}.jsonl`.

See `services/etl/README.md` for configuration and loader mapping.

### Hybrid store + RAG (Frame 3)

After ETL writes JSONL, the API Router calls **RAG Service :8002** `POST /ingest`.
RAG chunks with LangChain `RecursiveCharacterTextSplitter` (1000/200), embeds with
**Qwen3-VL-Embedding-2B** (2048-dim, multimodal, one shared space), stores **vector +
chunk text + `gridfs_id`** in **Chroma :8005**, and indexes metadata in local MongoDB
(`user_id` isolation). Premium chat (`POST /api/chat`) injects Top-k=3 context into
the LLM Service. `EMBEDDING_MOCK=true` keeps CI/laptops off the 2B weights.

See `services/rag/README.md`.

## Conventional Commits

This project uses [Conventional Commits](https://www.conventionalcommits.org/). See `CONTRIBUTING.md` for details.

## Tech stack

Python 3.13 · FastAPI · LangChain / LangGraph · React + Chart.js · React Native (iPhone) ·
MongoDB (local) · Chroma (local, 2048-dim) · Qwen3.5-4B (local container + on-device Q4) ·
Docker Compose · GitHub Actions.

**Auth:** JWT + bcrypt (register, login, `get_current_user`) with per-user data isolation.

**LLM_PROVIDER:** `ondevice` | `qwen_local` (alias `local`). Unsupported values fail at startup.

## Security

### Shift Left (Prevent in CI)

- **ruff**: Linting and code quality
- **pytest**: Unit and integration tests
- **Snyk**: Dependency scan and SAST (static analysis)

### Shift Right (Detect in Production)

- **CloudWatch**: Logs, metrics, alarms (future)
- **Rate limiting**: API Router locally; API Gateway in a future AWS deploy

### Data Encryption

- **Application-level**: Fernet for RAG embeddings and chunk text
- **Transport**: TLS when API Gateway exists (future)

## Budget

Targets **$0** using OSS; max pre-authorized ~$40 (Colab Pro + contingency).
