# Justificación — Platform foundation (Frame 1)

## El problema que resuelve

Antes de ETL, RAG o agentes, el repositorio necesita un contrato único:

1. Configuración validada al arranque (sin secretos en `/health`).
2. Autenticación JWT + bcrypt y aislamiento por `user_id`.
3. Un protocolo `LLMProvider` para Qwen3.5-4B on-device y Qwen3.5-4B base en contenedor.

## Patrones

| Pattern | Where | Purpose |
|---------|-------|---------|
| Strategy | `get_provider()` | `ondevice` vs `qwen_local` without caller changes |
| Protocol / DIP | `LLMProvider` | Depend on the chat/complete interface |
| Facade | FastAPI app | Single entry for health, auth, sample protected routes |
| Fail-fast | `validate_settings()` | Unsupported provider or missing `JWT_SECRET_KEY` never serves |

## SOLID

| Principle | Application |
|----------|-------------|
| S | Config, auth, providers, and routers are separate modules |
| O | New provider = new class; resolver grows by one branch |
| L | Any `LLMProvider` is substitutable in tests (HTTP mocked) |
| I | Chat/complete only; no Bedrock-specific surface |
| D | Routers depend on `get_current_user` and `get_provider()`, not AWS clients |

## Logs (correlation ID arrives in Frame 1.1)

```
2026-09-08T22:00:00 [no-id] INFO apps.api: GET /health
2026-09-08T22:00:01 [no-id] INFO apps.api: POST /auth/register
2026-09-08T22:00:02 [no-id] WARNING apps.api: GET /api/profile — Not authenticated
```
