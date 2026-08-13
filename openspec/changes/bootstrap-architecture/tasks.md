## 1. Repository conventions & CI

- [ ] 1.1 Pin dependency versions in `requirements.txt` (freeze the working set)
- [ ] 1.2 Add `.github/workflows/ci.yml` running `ruff` lint + `pytest` on push/PR
- [ ] 1.3 Add `ruff` configuration (`pyproject.toml`) and document GitHub Flow + conventional commits in `README`/`CONTRIBUTING`

## 2. Architecture documentation

- [ ] 2.1 Write C4 Level 1 (System Context) diagram as Mermaid in `docs/architecture/c4-context.md`
- [ ] 2.2 Write C4 Level 2 (Containers) diagram in `docs/architecture/c4-containers.md`
- [ ] 2.3 Write C4 Level 3 (Components) diagram for the API in `docs/architecture/c4-components.md`
- [ ] 2.4 Write the MCP agent-flow diagram (Ingestor → Razonador → Evaluador) in `docs/architecture/mcp-flow.md`
- [ ] 2.5 Write the OSS stack decision record (chosen tools + rationale) in `docs/architecture/stack.md`

## 3. Configuration layer

- [ ] 3.1 Implement `apps/api/config.py` using `pydantic-settings`, reading `.env` with safe defaults
- [ ] 3.2 Validate required secrets at startup; raise a clear, named error when the selected provider's key is missing
- [ ] 3.3 Keep `.env.example` in sync with all settings

## 4. Model-agnostic LLM provider layer

- [ ] 4.1 Define an `LLMProvider` protocol (chat/completion interface) in `apps/api/llm/base.py`
- [ ] 4.2 Implement the ollama (local proxy) provider
- [ ] 4.3 Implement the OpenRouter / OpenAI-compatible (cloud) provider
- [ ] 4.4 Implement a `get_provider()` resolver that selects by `LLM_PROVIDER` and fails fast on unsupported values

## 5. FastAPI application skeleton

- [ ] 5.1 Create `apps/api/main.py` with the FastAPI app and router mounting structure
- [ ] 5.2 Implement public `GET /health` returning `status` + resolved `llm_provider` (no secrets)
- [ ] 5.3 Implement basic-auth dependency and apply it to a sample protected endpoint

## 6. Tests

- [ ] 6.1 Test `/health` returns 200 with `status: ok` and no secrets leaked
- [ ] 6.2 Test config falls back to defaults and fails fast on a missing required secret
- [ ] 6.3 Test provider resolution: switching `LLM_PROVIDER` routes correctly; unsupported value fails fast (LLM calls mocked)
- [ ] 6.4 Test protected endpoint returns 401 without credentials and 200 with valid credentials
