## Context

This is the first change in a greenfield repo (empty git repo, Python 3.13). It is
cross-cutting: it defines the app skeleton and conventions that all remaining thesis modules
depend on. The project is a single-tenant platform with two subscription profiles (Free/Premium),
and a clear separation between local LLM inference (free) and AWS Bedrock with RAG + fine-tuning (premium).

See proposal.md — Why. Budget is ~$0 and the deployment target is a single-tenant MVP.
Choices favor OSS and local execution for development, with AWS ECS Fargate for production deployment.
AWS Bedrock provides both fine-tuning and inference for the premium tier.

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

### Single-Tenant with Subscription Profiles

The system supports two subscription profiles with different capabilities:

| Profile | LLM | Context | Files | Web Access |
|---------|-----|---------|-------|------------|
| Free | llama.rn (Llama 3.2 3B Q4_K_M) | No | No | No |
| Premium | AWS Bedrock (fine-tuned) + RAG | Yes | Yes (images + PDFs) | Yes |

**Rationale:** Single-tenant MVP with two profiles — one user with two profiles, or two users
with distinct subscriptions. Demonstrates model-agnosticism and tiered architecture.
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
| **LLM Layer** | llama.rn (local) / AWS Bedrock (cloud) | The actual LLM inference |

**Rationale:** The Tool Layer is not the model — it's the supporting infrastructure (vector
search, document retrieval, embeddings). The Layer is where inference happens. This separation
is critical for the C4 diagrams and for understanding the data flow. AWS Bedrock handles both
fine-tuning and inference for the premium tier.

### LLM Provider Abstraction

Provider selected by `LLM_PROVIDER` env var at runtime. Two implementations:
- **llama.rn**: on-device inference for quantized open-source models (Llama 3.2 3B Q4_K_M)
- **AWS Bedrock**: cloud provider for fine-tuned models (Llama 3 8B LoRA) + inference

**Rationale:** Keeps the model open per the user's requirement. Switching between providers
requires only a config change, not code changes. AWS Bedrock provides both fine-tuning and
inference for the premium tier, with free tier (750h/mes).

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
| Fine-Tuning | AWS Bedrock (LoRA, managed) | Managed service, free tier, integrates with inference |
| RAG | LangChain, Chroma/Pinecone | Industry standard for semantic retrieval |
| Document Store | MongoDB Atlas (M0 free tier) | Flexible schema for diverse document types |
| LLM Local | llama.rn (Llama 3.2 3B, Q4_K_M) | On-device inference, 18-25 tok/s, no cloud dependency |
| LLM Cloud | AWS Bedrock (Llama 3 8B fine-tuned + inference) | Managed service, free tier 750h/mes, fine-tuning + inference |
| Web | React + Chart.js | Matches anteproyecto stack |
| Mobile | React Native | Cross-platform, supports local LLM (llama.rn integration) |
| Infra Local | Docker Compose | Fast dev iteration |
| Infra Prod | AWS ECS Fargate | Serverless containers, no EC2 management |
| CI/CD | GitHub Actions | Free tier, matches stack |
| Encryption | Fernet (data), TLS (connection) | Simple, auditable, no external dependencies |

## Risks / Trade-offs

- [Local llama.rn not available in CI] → CI tests mock the LLM provider; live provider calls
  are exercised manually/locally, not in CI.
- [React Native + local LLM on mobile] → May require platform-specific optimizations;
  prototype early to validate feasibility.
- [Fine-tuning service complexity] → Keep it as a simple worker; expand only when a later
  module needs more sophisticated orchestration.
- [Config drift between environments] → Startup validation test asserts every required
  setting has a default or is documented in `.env.example`.
- [AWS costs] → Fargate + API Gateway are pay-per-use; MVP traffic should stay within
  free tier limits. Bedrock free tier (750h/mes) covers MVP inference needs.

## Limits and Assumptions (from anteproyecto)

### Users
- Included: 1 individual user (single-tenant) with two subscription profiles (Free/Premium)
- Out of scope: Multi-user, social sharing

### Languages
- Included: English (UI) + Spanish document support (LLM infers)
- Out of scope: Multilingual UI

### Platforms
- Included: Web app; proxy LLM runs on personal smartphone/laptop (modest CPU/GPU)
- Out of scope: Voice assistants

### Data Types
- Included: Text, PDF, static images
- Out of scope: Live audio streaming, video

### Security
- Included: Basic authentication
- Out of scope: AES-at-rest, HTTPS in transit, GDPR compliance, federated OAuth

### Privacy
- Included: On-device processing when possible; local logs
- Out of scope: Zero-knowledge cloud

### Continuous Learning
- Included: Regular manual fine-tuning triggered by agent or admin
- Out of scope: Real-time auto-retraining

### Scalability
- Included: 100 documents in DB, 1 GB embeddings
- Out of scope: High availability, sharding, thousands/millions of documents

### Simulations
- Included: Deterministic "what-if" analysis with simple decision tree
- Out of scope: Stochastic optimization, Monte Carlo simulation

### Fraud Detection
- Included: Heuristics + vector similarity in emails/SMS/messages
- Out of scope: Full-scale supervised models, voice spoofing

### Ethics and Governance
- Included: Responsible use guidelines, explainability panel
- Out of scope: External audit, ISO/IEC certifications

## Migration Plan

Not applicable — greenfield. Rollback = revert the change branch.

## Decisions Made

### Default Open-Source Model
- **Decision:** Llama 3.2 3B (on-device, free tier) + Llama 3 8B (cloud, premium tier)
- **Rationale:** 3B fits in 6GB RAM phones at 18-25 tok/s; 8B runs on Bedrock servers
  with no mobile constraints. Q4_K_M quantization for on-device (recommended for mobile).

### API Gateway
- **Decision:** AWS API Gateway (not Kong)
- **Rationale:** Managed service, free HTTPS certificates, rate limiting, routing.
  No DevOps overhead. Already in AWS ecosystem (ECS Fargate).

### Mobile LLM Integration
- **Decision:** `llama.rn` (not ollama-js, not react-native-ollama)
- **Rationale:** `llama.rn` is the React Native binding for llama.cpp — runs models
  ON DEVICE with GPU/NPU acceleration (Metal iOS, OpenCL Android).
  Ollama is a server runtime, not a mobile library. `llama.rn` loads GGUF models
  (same format as Ollama) directly on the device.
