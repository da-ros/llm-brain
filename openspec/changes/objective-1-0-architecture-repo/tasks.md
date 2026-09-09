## A. Architecture & Design (ANTES de código)

> La arquitectura es el artefacto principal de defensa (cuarto nivel).
> Los diagramas definen QUÉ construimos antes de decidir CÓMO.

- [x] A.1 C4 Level 1 (System Context) diagram — `output/diagrams/c4-context.drawio`
      — Clients (web/React Native mobile), API Router, backends, LLM layers (local container + on-device), data stores (AWS API Gateway shown as future)
- [x] A.2 C4 Level 2 (Containers) diagram — `output/diagrams/c4-container.drawio`
      — Docker containers: API Router, Fine-Tuning Service, RAG, LLM Service (Qwen3.5-4B), MongoDB, Chroma (AWS API Gateway shown as future)
- [x] A.3 C4 Level 3 (Components) diagram — `output/diagrams/c4-component-api.drawio`
      — Internal structure: FastAPI App, Config, Auth (JWT+bcrypt), LLM Provider Protocol, Routers, Dependencies
- [x] A.4 Deployment diagram (Docker Compose local MVP; AWS ECS Fargate as future) — `output/diagrams/deployment.drawio`
      — Local dev (direct client → API Router); production (via API Gateway) shown as future/out of scope
- [x] A.5 MCP agent-flow diagram — `output/diagrams/mcp-agent-flow.drawio`
- [x] A.6 OSS stack decision record — `docs/architecture/stack.md` and `output/documents/oss-stack.md`
- [x] A.7 Validate architecture with tutor / align on scope before proceeding to code
      — Scope aligned to `context.txt` (local Qwen3.5-4B, no Bedrock/Atlas). Record: `output/documents/tutor-alignment.md`

## B. Repository Foundation

> Establece las convenciones y estructura base antes de escribir código funcional.

- [x] B.1 Define project structure: create directories, `__init__.py` files, placeholder modules
      — `apps/api/`, `services/etl/`, `services/rag/`, `services/agents/`, etc.
- [x] B.2 Pin dependency versions in `requirements.txt` (freeze the working set)
- [x] B.3 Add `.gitignore` patterns, `CONTRIBUTING.md`, document conventional commits in `README`
- [x] B.4 Add `Dockerfile` + `docker-compose.yml` (local dev environment)
      — Services: API backend, MongoDB, Chroma
- [x] B.5 Add `.github/workflows/ci.yml` running `ruff` lint + `pytest` + Snyk on push/PR
      — CI pipeline includes: ruff (lint), pytest (tests), snyk test (dependency scan),
      snyk code test (SAST). This is the **Shift Left** security gate.
- [x] B.6 Add `ruff` configuration in `pyproject.toml`
- [x] B.7 Document security strategy: Shift Left (Snyk in CI) + future Shift Right (monitoring in prod)

## C. Configuration & Provider Layer

> El contrato que todos los módulos posteriores usan. Configuración validada al inicio.

- [x] C.1 Implement `apps/api/config.py` using `pydantic-settings`, reading `.env` with safe defaults
- [x] C.2 Validate required secrets at startup; raise clear error when provider key is missing
- [x] C.3 Keep `.env.example` in sync with all settings
- [x] C.4 Define `LLMProvider` protocol (chat/completion interface) in `apps/api/llm/base.py`
- [x] C.5 Implement on-device provider (React Native / Neural Engine / Metal — Free: Qwen3.5-4B base quantized Q4; Premium: fine-tuned quantized Q4)
- [x] C.6 Implement local containerized "cloud" provider (LLM Service 8003 — Qwen3.5-4B **base**, not fine-tuned)
- [x] C.7 Implement `get_provider()` resolver that selects by `LLM_PROVIDER` and fails fast on unsupported values

## D. FastAPI Application

> El artefacto ejecutable que todos los módulos montan.

- [x] D.1 Create `apps/api/main.py` with FastAPI app and router mounting structure
- [x] D.2 Implement public `GET /health` returning `status` + resolved `llm_provider` (no secrets)
- [x] D.3 Implement JWT auth dependency (replaces basic-auth)
- [x] D.4 Apply auth to a sample protected endpoint

## E. Tests

> Validación del contrato. Integrados con cada módulo, no como fase aparte.

- [x] E.1 Test `/health` returns 200 with `status: ok` and no secrets leaked
- [x] E.2 Test config falls back to defaults and fails fast on a missing required secret
- [x] E.3 Test provider resolution: switching `LLM_PROVIDER` routes correctly; unsupported value fails fast (LLM calls mocked)
- [x] E.4 Test protected endpoint returns 401 without credentials and 200 with valid credentials

## F. Architecture Validation (post-implementation)

> Verificar que la implementación es consistente con los diagramas C4.

- [x] F.1 Review C4 diagrams against implemented code — update diagrams if implementation diverged
- [x] F.2 Validate Docker Compose starts all services correctly
- [x] F.3 Run full test suite and confirm CI pipeline works end-to-end
- [x] F.4 Document any deviations from original architecture in `docs/architecture/decisions.md`
- [x] F.5 Frame output package: `output/diagrams/` (C4 + deployment + MCP) and `output/documents/`
