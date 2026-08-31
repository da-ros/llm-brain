# Justificación — API Router (Frame 1.1)

Explicación de los componentes clave del API Router (Gateway).

## El problema que resuelve

En una arquitectura de microservicios, el cliente no puede hablar directamente con cada servicio.
Necesita un **punto de entrada único** que maneje:

1. **Autenticación** — ¿Quién eres? (JWT)
2. **Enrutamiento** — ¿A qué servicio te conecto? (ETL, RAG, LLM)
3. **Trazabilidad** — ¿De dónde vino este request? (Correlation ID)
4. **Comunicación async** — ¿Cómo proceso cosas pesadas sin bloquear? (Kafka)
5. **Monitoreo** — ¿Cómo sé si algo terminó? (Task status polling)

---

## 📋 Logging Estructurado

### Formato estándar

```
{timestamp} [{correlation_id}] {level} {service}: {message}
```

### CorrelationFilter

Clase utilitaria que agrega `correlation_id` a todos los log records:

```python
class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = getattr(record, "correlation_id", "no-id")
        return True
```

### Helper log_with_correlation

```python
def log_with_correlation(correlation_id: str, level: str, message: str):
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)
```

---

## 📡 Logs por Endpoint

### GET /health (público)

```
2026-08-31T10:00:00 [no-id] INFO api-gateway: GET /health
```

### POST /api/upload (autenticado)

```
2026-08-31T10:00:00 [abc-123] INFO api-gateway: POST /api/upload
2026-08-31T10:00:00 [abc-123] INFO api-gateway: File saved to GridFS: receta.pdf (user_id=user1)
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Task status created: in_progress
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Published to Kafka: file.uploaded
```

### POST /api/chat (autenticado)

```
2026-08-31T10:00:00 [def-456] INFO api-gateway: POST /api/chat
2026-08-31T10:00:00 [def-456] INFO api-gateway: Calling RAG Service for context
2026-08-31T10:00:01 [def-456] INFO api-gateway: RAG context received: 3 sources
2026-08-31T10:00:01 [def-456] INFO api-gateway: Calling LLM Service for response
2026-08-31T10:00:02 [def-456] INFO api-gateway: LLM response received
```

### GET /tasks/:correlation_id (autenticado)

```
2026-08-31T10:00:05 [abc-123] INFO api-gateway: Polling task status: abc-123
2026-08-31T10:00:05 [abc-123] INFO api-gateway: Task status: success (retries=0)
```

### Errores de autenticación

```
2026-08-31T10:00:00 [no-id] WARNING api-gateway: POST /api/upload — Invalid token
2026-08-31T10:00:00 [no-id] WARNING api-gateway: Access denied — wrong user
```

---

## 📨 Logs por Kafka Producer

### Producer: file.uploaded

```
2026-08-31T10:00:00 [abc-123] INFO api-gateway: Publishing to Kafka: file.uploaded
2026-08-31T10:00:00 [abc-123] DEBUG api-gateway: Message: {correlation_id: abc-123, file_id: ObjectId(...), user_id: user1, filename: receta.pdf}
```

### Producer: task.response (retry)

```
2026-08-31T10:00:10 [abc-123] WARNING api-gateway: Retrying (1/3)
2026-08-31T10:00:10 [abc-123] INFO api-gateway: Republishing to Kafka: file.uploaded (retry)
```

---

## 📨 Logs por Kafka Consumer

### Consumer: task.response

```
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Consumed from Kafka: task.response
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Task response: success (http_code=200)
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Task completed successfully
```

### Consumer: error response (retry)

```
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Consumed from Kafka: task.response
2026-08-31T10:00:04 [abc-123] WARNING api-gateway: Task response: error (http_code=503)
2026-08-31T10:00:04 [abc-123] WARNING api-gateway: Retrying (1/3)
```

### Consumer: error response (DLQ)

```
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Consumed from Kafka: task.response
2026-08-31T10:00:04 [abc-123] ERROR api-gateway: Task response: error (http_code=500)
2026-08-31T10:00:04 [abc-123] ERROR api-gateway: Max retries reached — moved to DLQ
```

### Consumer: client error (no retry)

```
2026-08-31T10:00:04 [abc-123] INFO api-gateway: Consumed from Kafka: task.response
2026-08-31T10:00:04 [abc-123] ERROR api-gateway: Task failed (no retry): Unsupported file type
```

---

## 🔐 JWT Authentication — Logs

### Token válido

```
2026-08-31T10:00:00 [abc-123] DEBUG api-gateway: JWT validated: user_id=user1, tier=premium
```

### Token inválido

```
2026-08-31T10:00:00 [no-id] WARNING api-gateway: JWT validation failed: Invalid token
```

### Token expirado

```
2026-08-31T10:00:00 [no-id] WARNING api-gateway: JWT validation failed: Token expired
```

---

## 🔄 Retry Logic — Logs

### Retry exitoso

```
2026-08-31T10:00:10 [abc-123] WARNING api-gateway: Retrying (1/3) — re-publishing to Kafka
2026-08-31T10:00:15 [abc-123] INFO api-gateway: Retry succeeded — task completed
```

### Max retries alcanzado

```
2026-08-31T10:00:10 [abc-123] WARNING api-gateway: Retrying (3/3)
2026-08-31T10:00:15 [abc-123] ERROR api-gateway: Max retries reached — moved to DLQ
2026-08-31T10:00:15 [abc-123] ERROR api-gateway: Error: Connection timeout to ETL service
```

---

## 📊 Flujo Completo con Logs

### Upload exitoso

```
T+0.000s  [abc-123] INFO  api-gateway: POST /api/upload
T+0.001s  [abc-123] INFO  api-gateway: JWT validated: user_id=user1, tier=premium
T+0.002s  [abc-123] INFO  api-gateway: File saved to GridFS: receta.pdf
T+0.003s  [abc-123] INFO  api-gateway: Task status created: in_progress
T+0.004s  [abc-123] INFO  api-gateway: Published to Kafka: file.uploaded
T+0.005s  [abc-123] INFO  api-gateway: Response: 202 Accepted
T+1.000s  [abc-123] INFO  etl-service: Consumed from Kafka: file.uploaded
T+1.001s  [abc-123] INFO  etl-service: Fetching file from GridFS
T+1.500s  [abc-123] INFO  etl-service: Starting ETL pipeline
T+3.000s  [abc-123] INFO  etl-service: Extracted 15 triples
T+3.001s  [abc-123] INFO  etl-service: Published to Kafka: task.response (success)
T+3.500s  [abc-123] INFO  api-gateway: Consumed from Kafka: task.response
T+3.501s  [abc-123] INFO  api-gateway: Task completed successfully
T+5.000s  [abc-123] INFO  api-gateway: Polling task status: abc-123
T+5.001s  [abc-123] INFO  api-gateway: Task status: success (triples_count=15)
```

### Chat con RAG

```
T+0.000s  [def-456] INFO  api-gateway: POST /api/chat
T+0.001s  [def-456] INFO  api-gateway: JWT validated: user_id=user1, tier=premium
T+0.002s  [def-456] INFO  api-gateway: Calling RAG Service for context
T+0.500s  [def-456] INFO  rag-service: Semantic search: query='diabetes treatment' user=user1
T+1.000s  [def-456] INFO  rag-service: Search returned 3 results
T+1.001s  [def-456] INFO  api-gateway: RAG context received: 3 sources
T+1.002s  [def-456] INFO  api-gateway: Calling LLM Service for response
T+2.500s  [def-456] INFO  api-gateway: LLM response received
T+2.501s  [def-456] INFO  api-gateway: Response: 200 OK
```

### Error con retry

```
T+0.000s  [abc-789] INFO  api-gateway: POST /api/upload
T+0.004s  [abc-789] INFO  api-gateway: Published to Kafka: file.uploaded
T+1.000s  [abc-789] INFO  etl-service: Consumed from Kafka: file.uploaded
T+2.000s  [abc-789] ERROR etl-service: Processing failed: OCR engine not available
T+2.001s  [abc-789] ERROR etl-service: Published error response (http_code=500)
T+2.500s  [abc-789] INFO  api-gateway: Consumed from Kafka: task.response
T+2.501s  [abc-789] WARNING api-gateway: Retrying (1/3)
T+7.500s  [abc-789] INFO  etl-service: Consumed from Kafka: file.uploaded (retry)
T+8.500s  [abc-789] INFO  etl-service: Extracted 12 triples
T+8.501s  [abc-789] INFO  etl-service: Published success response
T+9.000s  [abc-789] INFO  api-gateway: Task completed successfully
```

---

## 🏗️ Patrones de Diseño y Principios SOLID

### Patrones aplicados

#### Facade (Fachada)
El API Router es una **fachada**: esconde toda la complejidad detrás de un solo endpoint:

```
Cliente solo ve:    POST /api/upload
Lo que pasa adentro: auth → validation → GridFS → Kafka → response
```

#### Middleware Pattern
Cross-cutting concerns (auth, correlation ID) se implementan como middleware:

```python
@app.middleware("http")
async def add_correlation_id(request, call_next):
    # Antes del request
    response = await call_next(request)
    # Después del request
    return response
```

#### Producer/Consumer
Kafka integra patrones Producer/Consumer para comunicación async:

```
Router (Producer) → Kafka → ETL (Consumer)
ETL (Producer) → Kafka → Router (Consumer)
```

#### Retry + DLQ
Manejo de errores con reintentos y Dead Letter Queue:

```
Error 5xx → Retry (retries < max)
Error 3xx/4xx → Fail (no retry)
Max retries → DLQ (permanent failure)
```

---

### Principios SOLID

| Principio | Aplicación |
|-----------|------------|
| **S** | Router solo maneja routing y auth; no tiene lógica de negocio |
| **O** | Agregar ruta nueva = crear router nuevo, cero cambios al main |
| **L** | Cualquier servicio puede ser llamado vía el mismo router |
| **I** | Router expone API mínima: upload, chat, tasks, health |
| **D** | Router depende de abstracciones (HTTP endpoints), no de implementaciones |
