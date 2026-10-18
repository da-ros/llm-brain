# Justificación — Privacy & Scam Shield (Frame 8)

El Shield Service (puerto **8009**) revisa texto, una imagen o un video corto
para usuarios **Premium**. Las heurísticas y la similitud de embeddings son
evidencia. **Qwen3.5-4B base** (`POST /chat`, temperature 0) devuelve
`likelihood`, `alert`, `severity`, `summary` y `rationale`. Solo si `alert`
es true se escribe `shield_incidents`.

## Veredicto del LLM, no un clasificador supervisado

`context.txt` pide heurísticas y similitud, y deja fuera un modelo de fraude
a escala. Esas dos señales entran en `reasons[]`. No deciden el alerta.

| | Clasificador supervisado | Solo heurísticas | Heurísticas + embed + LLM |
|--|--------------------------|------------------|---------------------------|
| Alcance del MVP | Fuera | Evidencia | Sí |
| Imagen o video | Habría que entrenarlo | No leen píxeles ni frames | El modelo es multimodal |
| Desacuerdo con una regla | El peso gana | La regla gana | Gana `alert` del modelo; la regla sigue en `reasons` |
| Fallo del modelo | — | Un falso positivo | **502/504** y no se persiste |

Un JSON inválido se reintenta una vez. El embed puede fallar: el scan sigue
y añade `embedding_unavailable`.

## `POST /embed` en lugar de abrir Chroma

Qwen3-VL-Embedding-2B ya vive en RAG (2048 dimensiones, texto, imagen y
video). Shield no carga esos pesos ni abre Chroma. `POST /embed` devuelve
el vector y no lo guarda. Al arranque se cachean los 30 textos de
`data/shield/corpus.jsonl`. El scan compara en proceso.

Buscar en el Chroma del usuario compararía contra sus notas, no contra el
corpus de estafas. Meter ese corpus en Chroma lo mezclaría con la búsqueda
personal.

## Contrato del Frame 7

`GET /api/shield/incidents` responde **200** con
`{ incidents: [{ id, created_at, severity, summary, source }] }`, también
cuando la lista está vacía. Un id de otro usuario es **404**.

## Patrones y SOLID

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| Chain of responsibility | `heuristics.py` | Cada regla añade un id |
| Strategy | OCR, embed, LLM | Tres pasos, un veredicto |
| Facade | API Router | El cliente no llama al 8009 |
| MCP | `scan_message` | Mismo contrato HTTP que las otras tools |
| Flyweight | vectores del corpus | No re-embeber 30 líneas |
| Idempotent command | `correlation_id` único | El reintento devuelve lo guardado |
| Graceful degradation | embed 5xx | El LLM igual corre |

| Principio | Aplicación |
|-----------|------------|
| **S** | Heurísticas, coseno, repositorio y guidelines van aparte |
| **O** | Un id nuevo no cambia las rutas |
| **L** | email, sms y message comparten el mismo scan |
| **I** | `/scan`, `/incidents`, `/guidelines` y MCP son contratos distintos |
| **D** | Shield depende de URLs, no de Chroma ni de los pesos |

`reason_graph` y `learn_graph` no cambian. Kafka no entra: el scan es HTTP
síncrono. Free recibe **403** y no llama a Shield.

## Logging estructurado

`CorrelationFilter`:

```
%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s
```

Si falta `X-Request-ID`, Shield genera un UUID, lo usa en RAG y en el LLM,
y lo devuelve.

### POST /scan

```
2026-09-24T01:40:00 [8f3a] INFO shield-service: POST /scan user_id=user1 source=image tier=premium
2026-09-24T01:40:00 [8f3a] INFO shield-service: OCR chars=42
2026-09-24T01:40:00 [8f3a] INFO shield-service: heuristics fired=['urgency', 'credential']
2026-09-24T01:40:01 [8f3a] INFO shield-service: nearest corpus_id=phish-01 score=0.9100
2026-09-24T01:40:02 [8f3a] INFO shield-service: persisted incident id=inc-1 correlation_id=8f3a
```

Ham (`alert` false): `alert false — not persisted`.

### RAG POST /embed

```
2026-09-24T01:40:00 [8f3a] INFO shield-service: RAG POST /embed http://rag-service:8002/embed modality=text
2026-09-24T01:40:00 [8f3a] INFO rag-service: POST /embed modality=text dim=2048 stored=false
```

### LLM POST /chat

```
2026-09-24T01:40:01 [8f3a] INFO shield-service: LLM POST /chat http://host.docker.internal:8003/chat temperature=0 model=Qwen3.5-4B
```

JSON inválido: `LLM JSON invalid — retry 1`. Tras el segundo fallo:
`LLM failure — no persist`.

### GET /incidents

```
2026-09-24T01:41:00 [8f3a] INFO shield-service: GET /incidents user_id=user1
```

### MCP scan_message

```
2026-09-24T01:42:00 [8f3a] INFO agents-service: MCP scan_message → Shield http://shield-service:8009/scan
```

El header `X-Request-ID` de esa llamada es el mismo `8f3a`.
