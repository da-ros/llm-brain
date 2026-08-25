## Context

This is the first change in a greenfield repo (empty git repo, Python 3.13). It is
cross-cutting: it defines the app skeleton and conventions that all remaining thesis modules
depend on. The project is a multi-tenant platform with web and mobile clients, two subscription
tiers (Free/Premium), and a clear separation between local LLM inference (free) and cloud LLM
with RAG + fine-tuning (premium).

See proposal.md — Why. Budget is ~$0 and the deployment target is a single-tenant MVP
that scales to multi-tenant architecture. Choices favor OSS and local execution for development,
with AWS ECS Fargate for production deployment.

## Goals / Non-Goals

**Goals:**
- A single mountable FastAPI app that later modules attach routers to.
- LLM access behind one interface so the concrete model is a config choice, not a code choice.
- Clear separation between local LLM (mobile free tier) and cloud LLM (premium tier with RAG).
- Architecture documented as C4 + deployment diagrams for the defense.
- Docker-based development and deployment (Docker Compose local, ECS Fargate production).
- CI that runs lint + tests on every push.

**Non-Goals:**
- No real ingestion, RAG, agents, or UI yet (those are later changes).
- No production hardening (AES-at-rest, OAuth, WAF) — explicitly out of thesis scope.
- No fine-tuning implementation here (Objetivo 4) — only the service skeleton.
- No API Gateway in local development — direct client → backend.

## Architecture Decisions

### Multi-Tenant with Subscription Tiers

The system supports two subscription tiers with different capabilities:

| Tier | LLM | Context | Files | Web Access |
|------|-----|---------|-------|------------|
| Free | ollama local (cuantizado) | No | No | No |
| Premium | LLM cloud (fine-tuned) + RAG | Yes | Yes (images + PDFs) | Yes |

**Rationale:** Matches thesis scope — demonstrates model-agnosticism and tiered architecture.
Free tier proves local inference works; premium tier proves RAG + fine-tuning integration.

### Two Backend Services

| Service | Responsibility | Scaling |
|---------|---------------|---------|
| API Backend | Auth, orchestration, REST endpoints, subscriptions | Horizontal (ECS tasks) |
| Fine-Tuning Service | Scheduled LoRA training, data processing | Separate ECS task, scales independently |

**Rationale:** Fine-tuning is compute-intensive and runs on schedule (not request-driven).
Separating it prevents training jobs from blocking user-facing API requests.

### LLM Tool Layer vs LLM Layer

| Layer | What | Purpose |
|-------|------|---------|
| **LLM Tool Layer** | RAG + Vector Store (Chroma/Pinecone) + MongoDB | Infrastructure that the LLM cloud uses for context retrieval |
| **LLM Layer** | ollama (local) / OpenRouter (cloud) | The actual LLM inference |

**Rationale:** The Tool Layer is not the model — it's the supporting infrastructure (vector
search, document retrieval, embeddings). The Layer is where inference happens. This separation
is critical for the C4 diagrams and for understanding the data flow.

### LLM Provider Abstraction

Provider selected by `LLM_PROVIDER` env var at runtime. Two implementations:
- **ollama**: local proxy for quantized open-source models (Qwen/DeepSeek/GLM GGUF-Q4)
- **OpenRouter**: cloud provider for fine-tuned or larger models

**Rationale:** Keeps the model open per the user's requirement. Switching between providers
requires only a config change, not code changes.

### Deployment Strategy

| Environment | Infrastructure | API Gateway |
|-------------|---------------|-------------|
| **Local** | Docker Compose | None (direct client → backend) |
| **Production** | AWS ECS Fargate | AWS API Gateway (managed HTTPS) |

**Rationale:**
- Local: Docker Compose for fast development iteration. No API Gateway complexity.
- Production: ECS Fargate for serverless containers (no EC2 management). AWS API Gateway
  provides HTTPS certificates for free, rate limiting, and routing.
- Fine-Tuning Service runs as a separate ECS task for independent scaling.

### Configuration Management

- **pydantic-settings** for typed config loaded from environment variables
- `.env` file for local development
- ECS Task Definition environment variables for production
- Secrets (API keys) via environment variables, never hardcoded

**Rationale:** 12-factor app approach. Works in both Docker Compose and ECS without code changes.

### Authentication

- Basic auth via FastAPI dependency for protected endpoints
- `GET /health` left public (no secrets exposed)
- No JWT/OAuth in MVP scope

**Rationale:** Matches "autenticación básica" scope. Simple to test and demonstrate.

### Security Strategy: Shift Left + Shift Right

```
DESARROLLO                                          PRODUCCIÓN
◄───────────────────────────────────┼───────────────────────────────────►
                                    │
        SHIFT LEFT                 │              SHIFT RIGHT
   (prevenir en CI)                │    (detectar en runtime)
                                    │
   • ruff (linting)                 │   • Health checks
   • pytest (tests)                 │   • Rate limiting logs
   • snyk test (deps)              │   • Anomaly detection
   • snyk code test (SAST)         │   • Monitoring (futuro)
   • Secret scanning               │
```

**Shift Left (MVP — implemented now):**
- `snyk test --file=requirements.txt` — scans dependencies for known vulnerabilities
- `snyk code test` — static application security testing (SAST) on Python code
- Both run in GitHub Actions CI on every push/PR
- Snyk free tier: 200 tests/month, sufficient for MVP

**Shift Right (future modules):**
- Centralized logging (CloudWatch or similar)
- Rate limiting monitoring via API Gateway metrics
- Anomaly detection on LLM usage patterns
- Alerting on suspicious access patterns

**Rationale:** Security is a thesis concern (Objetivo 8 — Privacy & Scam Shield). Shift Left
catches vulnerabilities early at zero cost (Snyk free tier). Shift Right will be implemented
in later modules when production monitoring is needed.

### Data Encryption

- **TLS**: managed by AWS API Gateway (production). Local uses plain HTTP.
- **Application-level encryption**: Fernet symmetric encryption for data in RAG
  (documents, embeddings at rest)

**Rationale:** AWS API Gateway provides HTTPS certificates at no cost. Application-level
encryption protects sensitive user data (medical records, financial documents) in the
vector store and document database.

### Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Backend API | Python 3.13, FastAPI | Async-friendly, first-class pytest + httpx testing |
| Fine-Tuning | Python, llama-cpp-python, LoRA | Matches thesis stack |
| RAG | LangChain, Chroma/Pinecone | Industry standard for semantic retrieval |
| Document Store | MongoDB Atlas (M0 free tier) | Flexible schema for diverse document types |
| LLM Local | ollama (GGUF-Q4 cuantizado) | Runs on mobile device, no cloud dependency |
| LLM Cloud | OpenRouter / OpenAI-compat | Model-agnostic, supports fine-tuned models |
| Web | React + Chart.js | Matches anteproyecto stack |
| Mobile | React Native | Cross-platform, supports local LLM (ollama integration) |
| Infra Local | Docker Compose | Fast dev iteration |
| Infra Prod | AWS ECS Fargate | Serverless containers, no EC2 management |
| CI/CD | GitHub Actions | Free tier, matches stack |
| Encryption | Fernet (data), TLS (connection) | Simple, auditable, no external dependencies |

## Risks / Trade-offs

- [Local ollama not available in CI] → CI tests mock the LLM provider; live provider calls
  are exercised manually/locally, not in CI.
- [React Native + local LLM on mobile] → May require platform-specific optimizations;
  prototype early to validate feasibility.
- [Fine-tuning service complexity] → Keep it as a simple worker; expand only when a later
  module needs more sophisticated orchestration.
- [Config drift between environments] → Startup validation test asserts every required
  setting has a default or is documented in `.env.example`.
- [AWS costs] → Fargate + API Gateway are pay-per-use; MVP traffic should stay within
  free tier limits.

## Migration Plan

Not applicable — greenfield. Rollback = revert the change branch.

## Open Questions

- Concrete default open-source model tag (e.g. `qwen2.5:7b`) can be tuned later in the
  fine-tuning change (Objetivo 4) without affecting this contract.
- API Gateway: AWS API Gateway vs Kong — AWS recommended for simplicity (no devops overhead).
  Kong could be considered later if more control is needed.
- Mobile LLM integration: `react-native-ollama` vs `llama.rn` — prototype needed to validate.
