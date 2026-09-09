# Justificación — API Router (Frame 1.1)

El API Router es el **punto de entrada único** del MVP local. El cliente no habla
con ETL, RAG o LLM: habla con FastAPI en el puerto 8000.

## El problema que resuelve

1. **Autenticación** — JWT en el borde (`user_id`, `subscription_tier` / `tier`).
2. **Trazabilidad** — `X-Request-ID` (UUID) en cada request y en cada línea de log.
3. **Enrutamiento** — upload async (Kafka), chat sync (HTTP), health público.
4. **Estado async** — `GET /tasks/:correlation_id` sobre MongoDB (`task_status` + TTL).
5. **Recuperación** — retry 5xx, fail 3xx/4xx, DLQ (`task.dlq`) al agotar `MAX_RETRIES`.
6. **Rate limiting local** — AWS API Gateway es futuro / fuera de MVP.

El router **no** extrae triples, **no** hace embeddings y **no** genera texto: solo
autentica, limita, enruta y actualiza estado.

## Módulos (SRP)

| Módulo | Responsabilidad |
|--------|-----------------|
| `main.py` | App FastAPI, middleware de correlation ID, montaje de routers, lifespan |
| `config.py` | pydantic-settings; falla si falta `JWT_SECRET_KEY` |
| `auth.py` | `verify_token`, `require_premium` |
| `rate_limit.py` | Sliding window in-memory (upload / chat / tasks) |
| `db.py` | GridFS + `task_status` + índice TTL `expires_at` |
| `kafka_io.py` | Producer `file.uploaded`, consumer `task.response`, DLQ `task.dlq` |
| `routers/health.py` | `GET /health` público, `service: api-gateway` |
| `routers/upload.py` | `POST /api/upload` Premium → 202 |
| `routers/chat.py` | `POST /api/chat` → RAG (premium) + LLM |
| `routers/tasks.py` | `GET /tasks/:id` con aislamiento por `user_id` |

## Logging estructurado

Formato:

```
{timestamp} [{correlation_id}] {level} {service}: {message}
```

`CorrelationFilter` rellena `correlation_id` desde un `ContextVar`. Helper:
`log_with_correlation(id, level, message)`. Logger: `api-gateway`.

```
2026-08-31T10:00:00 [abc-123] INFO api-gateway: POST /api/upload
2026-08-31T10:00:00 [abc-123] INFO api-gateway: File saved to GridFS: receta.pdf (user_id=user1)
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Task status created: in_progress
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Published to Kafka: file.uploaded
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Response: 202 Accepted
```

Health (sin JWT):

```
2026-08-31T10:00:00 [550e8400-e29b-41d4-a716-446655440000] INFO api-gateway: GET /health
```

Chat premium:

```
2026-08-31T10:00:00 [def-456] INFO api-gateway: POST /api/chat
2026-08-31T10:00:00 [def-456] INFO api-gateway: Calling RAG Service for context
2026-08-31T10:00:01 [def-456] INFO api-gateway: RAG context received: 3 sources
2026-08-31T10:00:01 [def-456] INFO api-gateway: Calling LLM Service for response
2026-08-31T10:00:02 [def-456] INFO api-gateway: Response: 200 OK
```

Retry / DLQ:

```
2026-08-31T10:00:04 [abc-123] WARNING api-gateway: Retrying (1/3) — re-publishing to Kafka
2026-08-31T10:00:15 [abc-123] ERROR api-gateway: Max retries reached — moved to DLQ (task.dlq)
2026-08-31T10:00:04 [abc-123] ERROR api-gateway: Task failed (no retry): Unsupported file type
```

## Patrones

| Pattern | Where | Purpose |
|---------|-------|---------|
| Facade / API Gateway | API Router | Un solo endpoint de cliente; AWS API Gateway es futuro |
| Middleware | `add_correlation_id` | Cross-cutting tracing |
| Producer / Consumer | `kafka_io.py` | Upload async desacoplado de ETL |
| Retry + DLQ | `classify_response` | 5xx reintenta; 3xx/4xx no; máximo → `dlq-max` |
| Dependency injection | FastAPI `Depends` | JWT y rate limit por ruta, health sin auth |

## SOLID

| Principio | Aplicación |
|-----------|------------|
| **S** | Routing/auth en el router; ETL/RAG/LLM en sus servicios |
| **O** | Nueva ruta = nuevo archivo en `routers/`, `create_app()` solo monta |
| **L** | Cualquier servicio HTTP se llama con la misma fachada (URL + `X-Request-ID`) |
| **I** | Superficie mínima: upload, chat, tasks, health |
| **D** | El router depende de URLs (`RAG_SERVICE_URL`, `LLM_SERVICE_URL`) y de Kafka, no de implementaciones internas |

## Contratos HTTP

| Ruta | Auth | Resultado |
|------|------|-----------|
| `GET /health` | No | 200 `{status, service: api-gateway, version}` sin secretos |
| `POST /api/upload` | JWT Premium | 202 `{correlation_id}` · Free → 403 · MIME inválido → 422 |
| `POST /api/chat` | JWT | 200 `{response, correlation_id}` · RAG solo premium |
| `GET /tasks/:id` | JWT | 200 estado · 404 ausente · 403 otro usuario |
