## A. Architecture & Design (ANTES de código)

> La arquitectura es el artefacto principal de defensa (cuarto nivel).
> Los diagramas definen QUÉ construimos antes de decidir CÓMO.

- [ ] A.1 Write C4 Level 1 (System Context) diagram as Mermaid in `docs/architecture/c4-context.md`
      — Clients (web/mobile), API Gateway, backends, LLM layers, data stores, external systems
- [ ] A.2 Write C4 Level 2 (Containers) diagram in `docs/architecture/c4-containers.md`
      — Docker containers: API Backend, Fine-Tuning Service, RAG, MongoDB, Chroma, ollama, API Gateway
- [ ] A.3 Write C4 Level 3 (Components) diagram for the API in `docs/architecture/c4-components.md`
      — Internal structure: auth, config, LLM provider layer, routers
- [ ] A.4 Write the MCP agent-flow diagram (Ingestor → Razonador → Evaluador) in `docs/architecture/mcp-flow.md`
- [ ] A.5 Write the deployment diagram (Docker Compose local + AWS ECS Fargate) in `docs/architecture/deployment.md`
      — Two views: local dev (direct client → backend) and production (via API Gateway)
- [ ] A.6 Write the OSS stack decision record (chosen tools + rationale) in `docs/architecture/stack.md`
      — Document every technology choice and WHY it was selected
- [ ] A.7 Validate architecture with tutor / align on scope before proceeding to code

## B. Repository Foundation

> Establece las convenciones y estructura base antes de escribir código funcional.

- [ ] B.1 Define project structure: create directories, `__init__.py` files, placeholder modules
      — `apps/api/`, `services/etl/`, `services/rag/`, `services/agents/`, etc.
- [ ] B.2 Pin dependency versions in `requirements.txt` (freeze the working set)
- [ ] B.3 Add `.gitignore` patterns, `CONTRIBUTING.md`, document conventional commits in `README`
- [ ] B.4 Add `Dockerfile` + `docker-compose.yml` (local dev environment)
      — Services: API backend, MongoDB, Chroma, ollama
- [ ] B.5 Add `.github/workflows/ci.yml` running `ruff` lint + `pytest` + Snyk on push/PR
      — CI pipeline includes: ruff (lint), pytest (tests), snyk test (dependency scan),
      snyk code test (SAST). This is the **Shift Left** security gate.
- [ ] B.6 Add `ruff` configuration in `pyproject.toml`
- [ ] B.7 Document security strategy: Shift Left (Snyk in CI) + future Shift Right (monitoring in prod)

## C. Configuration & Provider Layer

> El contrato que todos los módulos posteriores usan. Configuración validada al inicio.

- [ ] C.1 Implement `apps/api/config.py` using `pydantic-settings`, reading `.env` with safe defaults
- [ ] C.2 Validate required secrets at startup; raise clear error when provider key is missing
- [ ] C.3 Keep `.env.example` in sync with all settings
- [ ] C.4 Define `LLMProvider` protocol (chat/completion interface) in `apps/api/llm/base.py`
- [ ] C.5 Implement ollama provider (local proxy for quantized models)
- [ ] C.6 Implement OpenRouter / OpenAI-compatible provider (cloud)
- [ ] C.7 Implement `get_provider()` resolver that selects by `LLM_PROVIDER` and fails fast on unsupported values

## D. FastAPI Application

> El artefacto ejecutable que todos los módulos montan.

- [ ] D.1 Create `apps/api/main.py` with FastAPI app and router mounting structure
- [ ] D.2 Implement public `GET /health` returning `status` + resolved `llm_provider` (no secrets)
- [ ] D.3 Implement basic-auth dependency
- [ ] D.4 Apply auth to a sample protected endpoint

## E. Tests

> Validación del contrato. Integrados con cada módulo, no como fase aparte.

- [ ] E.1 Test `/health` returns 200 with `status: ok` and no secrets leaked
- [ ] E.2 Test config falls back to defaults and fails fast on a missing required secret
- [ ] E.3 Test provider resolution: switching `LLM_PROVIDER` routes correctly; unsupported value fails fast (LLM calls mocked)
- [ ] E.4 Test protected endpoint returns 401 without credentials and 200 with valid credentials

## F. Architecture Validation (post-implementation)

> Verificar que la implementación es consistente con los diagramas C4.

- [ ] F.1 Review C4 diagrams against implemented code — update diagrams if implementation diverged
- [ ] F.2 Validate Docker Compose starts all services correctly
- [ ] F.3 Run full test suite and confirm CI pipeline works end-to-end
- [ ] F.4 Document any deviations from original architecture in `docs/architecture/decisions.md`
