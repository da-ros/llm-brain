## Why

The thesis MVP (Objetivo Específico 1) requires an approved technical/functional architecture
and a working repository foundation before any module is built. Every later module (ETL, RAG,
MCP agents, simulator, analytics, shield) depends on a shared, model-agnostic service skeleton,
a documented C4/MCP architecture, and a minimal CI pipeline. Establishing this first prevents
rework and gives the defense a traceable starting point.

## What Changes

- Add a documented **C4 architecture** (context, containers, components) and an **MCP agent-flow
  diagram** (Ingestor / Razonador / Evaluador) plus the OSS stack decision record under `docs/`.
- Add a minimal **FastAPI backend skeleton** (`apps/api/`) exposing a health endpoint and basic
  authentication, so all future modules mount onto one app.
- Add a **model-agnostic LLM provider layer**: the active model/provider (open-source models such
  as Qwen/DeepSeek/GLM via a local ollama proxy, or cloud via OpenRouter) is resolved from
  configuration/environment, never hardcoded.
- Add centralized **configuration loading** from environment (`.env`) with safe defaults.
- Add **CI** (GitHub Actions) running lint + tests, and repository conventions (GitHub Flow,
  conventional commits, pinned dependencies).

## Capabilities

### New Capabilities
- `platform-foundation`: the shared application foundation — configuration loading, a health
  endpoint, basic authentication, and model-agnostic LLM provider resolution that every other
  module builds on.

### Modified Capabilities
<!-- None: this is the first change; there are no existing specs to modify. -->

## Impact

- New code: `apps/api/` (FastAPI app, config, auth, LLM provider layer).
- New docs: `docs/architecture/` (C4 + MCP diagram + stack decision).
- New infra: `.github/workflows/` CI, `requirements.txt` pinning.
- Dependencies introduced: FastAPI, uvicorn, pydantic-settings, httpx/openai (LLM clients).
- No user data is processed yet; establishes the contract for all subsequent modules.
