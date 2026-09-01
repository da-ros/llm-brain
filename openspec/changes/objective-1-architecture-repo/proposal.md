## Why

The thesis MVP (Objetivo Específico 1) requires an approved technical/functional architecture
and a working repository foundation before any module is built. Every later module (ETL, RAG,
MCP agents, simulator, analytics, shield) depends on a shared, model-agnostic service skeleton,
a documented C4/MCP architecture, and a minimal CI pipeline. Establishing this first prevents
rework and gives the defense a traceable starting point.

This is a **multi-tenant platform** with two subscription tiers (Free/Premium). Each user
registers, authenticates (JWT + bcrypt), and has isolated data. Local LLM inference (free)
and AWS Bedrock with RAG + fine-tuning (premium).

The anteproyecto mentions "one user" referring to the data inputter for fine-tuning.
The platform supports multiple real users from the MVP.

## What Changes

### Architecture Documentation (C4 + Deployment)
- Add **C4 Level 1** (System Context): clients, API Gateway, backends, LLM layers, data stores
- Add **C4 Level 2** (Containers): Docker containers for each service
- Add **C4 Level 3** (Components): internal structure of the API backend
- Add **MCP agent-flow diagram**: Ingestor / Razonador / Evaluador
- Add **Deployment diagram**: Docker Compose (local) + AWS ECS Fargate (production)
- Add **OSS stack decision record**: chosen tools + rationale

### Repository Foundation
- Define project structure (directories, modules)
- Pin dependency versions in `requirements.txt`
- Add CI pipeline (GitHub Actions: ruff + pytest)
- Add Docker base (Dockerfile + docker-compose.yml)
- Add repository conventions (GitHub Flow, conventional commits)

### Configuration Layer
- Implement config loading from environment (pydantic-settings + .env)
- Validate required secrets at startup
- Support two environments: local (direct) and production (via API Gateway)

### Model-Agnostic LLM Provider Layer
- Define `LLMProvider` protocol (chat/completion interface)
- Implement llama.rn provider (on-device, mobile free tier — Llama 3.2 3B Q4_K_M)
- Implement AWS Bedrock provider (cloud, premium tier — Llama 3 8B fine-tuned + inference)
- Implement `get_provider()` resolver

### FastAPI Application Skeleton
- Create main.py with app + router mounting
- Implement `GET /health` (public)
- Implement JWT auth: register, login, verify_token, get_current_user
- Implement subscription tier enforcement via FastAPI dependency
- Sample protected endpoint demonstrating per-user data isolation

### Tests
- Test `/health` returns 200 + no secrets leaked
- Test config defaults + fail-fast on missing secret
- Test provider resolution (mocked LLM calls)
- Test JWT auth: register → login → access protected endpoint (401 without token, 200 with valid token)
- Test subscription tier enforcement

## Capabilities

### New Capabilities
- `platform-foundation`: shared application foundation — configuration, health endpoint,
  JWT authentication (register/login/verify), user data model, and model-agnostic LLM provider resolution

### Modified Capabilities
<!-- None: this is the first change; there are no existing specs to modify. -->

## Impact

- New code: `apps/api/` (FastAPI app, config, auth, LLM provider layer)
- New docs: `docs/architecture/` (C4 + MCP + deployment diagrams + stack decision)
- New infra: Docker Compose (local), ECS task definitions (production), GitHub Actions CI
- Dependencies introduced: FastAPI, uvicorn, pydantic-settings, httpx/openai (LLM clients)
- No user data is processed yet; establishes the contract for all subsequent modules

## Execution Order

The tasks are sequenced **architecture-first**:

1. **Document the system** (C4 diagrams) — defines WHAT we build
2. **Decide the stack with rationale** — defines HOW we build it
3. **Set up repo conventions** — establishes the foundation
4. **Build config + provider layer** — the contract everything mounts on
5. **Scaffold the API** — the runnable artifact
6. **Test everything** — validates the contract

Rationale: this is a 4th-level master's thesis in Software Architecture. The architecture
documentation is the primary defense artifact. Code supports the architecture, not the other
way around.
