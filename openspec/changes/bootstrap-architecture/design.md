## Context

This is the first change in a greenfield repo (empty git repo, Node 22, Python 3.13). It is
cross-cutting: it defines the app skeleton and conventions that all 8 remaining thesis modules
depend on. See proposal.md — Why. Budget is ~$0 and the deployment target is a single-tenant,
local-first MVP, so choices favor OSS and local execution.

## Goals / Non-Goals

**Goals:**
- A single mountable FastAPI app that later modules attach routers to.
- LLM access behind one interface so the concrete model is a config choice, not a code choice.
- Architecture documented as C4 + an MCP agent-flow diagram for the defense.
- CI that runs lint + tests on every push.

**Non-Goals:**
- No real ingestion, RAG, agents, or UI yet (those are later changes).
- No production hardening (HTTPS, AES-at-rest, OAuth) — explicitly out of thesis scope.
- No fine-tuning here (Objetivo 4).

## Decisions

- **FastAPI + uvicorn** for the backend. Rationale: matches the anteproyecto stack, async-friendly,
  first-class for pytest + httpx integration testing (needed for Objetivo 9 KPIs). Alternative:
  Flask — rejected for weaker async/testing ergonomics.
- **`pydantic-settings` for config** loaded from environment/`.env`. Rationale: typed, validates at
  startup, supports safe defaults. Alternative: raw `os.environ` — rejected (no validation).
- **LLM provider abstraction** (`LLMProvider` protocol with `ollama` and `openrouter`/OpenAI-compatible
  implementations), selected by `LLM_PROVIDER`. Rationale: keeps the model open (Qwen/DeepSeek/GLM or
  cloud) per the user's requirement. Alternative: hardcode one SDK — rejected (defeats model-agnosticism).
- **Basic auth via FastAPI dependency**, `/health` left public. Rationale: matches "autenticación
  básica" scope; simple to test. Alternative: JWT/OAuth — out of scope.
- **C4 + MCP diagrams as Mermaid in Markdown** under `docs/architecture/`. Rationale: versionable,
  diffable, renders in GitHub/Cursor. Alternative: binary Figma/draw.io exports — rejected (not diffable).
- **CI = GitHub Actions** running `ruff` + `pytest`. Rationale: free tier, matches stack.

## Risks / Trade-offs

- [Local ollama not always available in CI] → CI tests mock the LLM provider; live provider calls
  are exercised manually/locally, not in CI.
- [Over-engineering the skeleton] → Keep the provider layer to two implementations and a protocol;
  expand only when a later module needs it.
- [Config drift between `.env.example` and code] → A startup validation test asserts every required
  setting has a default or is documented in `.env.example`.

## Migration Plan

Not applicable — greenfield. Rollback = revert the change branch.

## Open Questions

- None blocking. Concrete default open-source model tag (e.g. `qwen2.5:7b`) can be tuned later in the
  fine-tuning change (Objetivo 4) without affecting this contract.
