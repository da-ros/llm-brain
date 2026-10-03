# Justificación — LLM Service (Frame 4)

El LLM Service es el **contenedor local** que sirve **Qwen3.5-4B base** (sin
fine-tuning) en el puerto 8003. "Cloud" en el MVP = este proceso Docker en la
laptop. AWS Bedrock, Llama y APIs gestionadas quedan fuera de alcance.

## El problema que resuelve

1. **Inferencia web** — `POST /generate` y `POST /chat` (texto, imagen, video)
   para Free y Premium. Los dos usan el mismo modelo base. Free web no trae
   RAG ni memoria. Timeout 30s. Respuesta `{response, tokens_used}`.
2. **Extracción de triples** — `POST /extract` para el ETL (Frame 2). El modelo
   base razona sobre el documento; no hace falta LoRA para extraer triples.
3. **Free del iPhone no entra aquí** — ese chat se queda en el Q4 base del
   teléfono (Frame 10). Un `tier` distinto de `free` o `premium` responde 400.
4. **Trazabilidad** — propaga `X-Request-ID`; no genera un UUID nuevo.

El servicio **no** entrena, **no** aplica adapters LoRA y **no** llama a la nube.

## Módulos (SRP)

| Módulo | Responsabilidad |
|--------|-----------------|
| `main.py` | App FastAPI, middleware de correlation ID, montaje de routers |
| `config.py` | pydantic-settings: `QWEN_MODEL_ID`, timeout, `QWEN_MOCK` |
| `logging_setup.py` | `CorrelationFilter` + `log_with_correlation` |
| `exceptions.py` | `ModelUnavailableError`, `ModelNotFoundError`, `InferenceTimeoutError` |
| `providers/base.py` | Protocol `LLMProvider` + `LLMResult` |
| `providers/qwen_local.py` | Inferencia local (mock en CI; transformers si `QWEN_MOCK=false`) |
| `providers/resolver.py` | `free` y `premium` → el mismo `QwenLocalProvider` base |
| `routers/health.py` | `GET /health` público, `provider: qwen-local-container` |
| `routers/generate.py` | `POST /generate` |
| `routers/chat.py` | `POST /chat` multimodal + RAG `context` |
| `routers/extract.py` | `POST /extract` triples JSON |

## Logging estructurado

```
{timestamp} [{correlation_id}] {level} llm-service: {message}
```

```
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate
2026-08-31T10:00:00 [abc-123] INFO llm-service: POST /generate — prompt length: 45 chars
2026-08-31T10:00:01 [abc-123] INFO llm-service: Qwen3.5-4B response: 150 tokens
```

Health:

```
2026-08-31T10:00:00 [no-id] INFO llm-service: GET /health
```

Errores:

```
2026-08-31T10:00:00 [def-456] WARNING llm-service: Invalid tier: unknown
2026-08-31T10:00:01 [ghi-789] ERROR llm-service: Qwen3.5-4B container/model error: Qwen3.5-4B container unavailable
2026-08-31T10:00:01 [jkl-012] ERROR llm-service: Qwen3.5-4B inference timeout
```

## Patrones

| Pattern | Where | Purpose |
|---------|-------|---------|
| Strategy | `get_provider(tier)` | Web free y Premium = el mismo contenedor base |
| Adapter | `QwenLocalProvider` | HuggingFace / mock → Protocol `chat` / `complete` |
| DIP | routers dependen de `LLMProvider`, no de transformers |

## SOLID

| Principio | Aplicación |
|-----------|-----------|
| **S** | Un provider, un runtime, un endpoint por verbo |
| **O** | Otro backend local se agrega implementando el Protocol |
| **L** | Cualquier `LLMProvider` es sustituible en los routers |
| **I** | Solo `chat()` y `complete()` |
| **D** | Routers → Protocol, no → Qwen weights |

## Errores HTTP

| Caso | Código |
|------|--------|
| Prompt / messages / user_id faltante | 400 |
| Tier distinto de free o premium | 400 |
| Contenedor o pesos ausentes | 500 |
| Timeout de inferencia | 504 |
