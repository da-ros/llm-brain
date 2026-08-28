## A. Architecture & Design (ANTES de código)

> La arquitectura es el artefacto principal de defensa (cuarto nivel).
> Los diagramas definen QUÉ construimos antes de decidir CÓMO.

- [x] A.1 C4 Level 1 (System Context) diagram — `diagrams/c4-context.drawio`
      — Clients (web/mobile), API Gateway, backends, LLM layers, data stores, external systems
- [x] A.2 C4 Level 2 (Containers) diagram — `diagrams/c4-container.drawio`
      — Docker containers: API Backend, Fine-Tuning Service, RAG, MongoDB, Chroma, API Gateway
- [x] A.3 C4 Level 3 (Components) diagrams — `diagrams/c4-component-api.drawio`, `diagrams/c4-component-mobile.drawio`
      — Internal structure: auth, config, LLM provider layer, routers, mobile components
- [x] A.4 MCP agent-flow diagram (Ingestor → Razonador → Evaluador) — `diagrams/mcp-agent-flow.drawio`
- [x] A.5 Deployment diagram (Docker Compose local + AWS ECS Fargate) — `diagrams/deployment.drawio`
      — Two views: local dev (direct client → backend) and production (via API Gateway)
- [x] A.6 OSS stack decision record (chosen tools + rationale) — `diagrams/tech-stack.drawio`
      — Document every technology choice and WHY it was selected
- [ ] A.7 Validate architecture with tutor / align on scope before proceeding to code

## B. Repository Foundation

> Establece las convenciones y estructura base antes de escribir código funcional.

- [ ] B.1 Define project structure: create directories, `__init__.py` files, placeholder modules
      — `apps/api/`, `services/etl/`, `services/rag/`, `services/agents/`, etc.
- [ ] B.2 Pin dependency versions in `requirements.txt` (freeze the working set)
- [ ] B.3 Add `.gitignore` patterns, `CONTRIBUTING.md`, document conventional commits in `README`
- [ ] B.4 Add `Dockerfile` + `docker-compose.yml` (local dev environment)
      — Services: API backend, MongoDB, Chroma
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
- [ ] C.5 Implement llama.rn provider (on-device — Llama 3.2 3B Q4_K_M)
- [ ] C.6 Implement AWS Bedrock provider (cloud — Llama 3 8B fine-tuned + inference)
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
