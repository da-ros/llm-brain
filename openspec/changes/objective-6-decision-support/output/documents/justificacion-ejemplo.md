# Justificación — Decision-Support Simulator (Frame 6)

El Simulator Service (puerto **8007**) responde “¿y si…?” para usuarios
**Premium**. Un árbol de decisión elige de 3 a 5 hojas con una traza de
nodos. **Qwen3.5-4B base** (`POST /chat`, temperature 0) redacta el título,
el desenlace y las asunciones de cada hoja. El resultado se guarda en
MongoDB `simulations`, aislado por `user_id`.

El paquete `services/simulator/` existía vacío desde el Frame 1. Esta
entrega lo llena y registra la herramienta MCP `simulate_whatif` y las
rutas del API Router. El chat de Frame 5 no cambia: `reason_graph` no
enruta solo las preguntas what-if.

---

## Por qué árbol + LLM (y no Monte Carlo)

`context.txt` pide un what-if **determinista** con un árbol simple y 3–5
escenarios con asunciones explícitas. Monte Carlo y la búsqueda estocástica
quedan fuera del MVP.

| Necesidad Frame 6 | Solo plantillas | Solo LLM | Monte Carlo | Árbol + LLM |
|-------------------|-----------------|----------|-------------|-------------|
| Siempre 3–5 futuros auditables | Sí, pero rígidos | El modelo puede devolver 1 o 12 | N muestras | El árbol fija las hojas; el tope es 5 |
| Misma pregunta → misma traza | Sí | No | No (semilla) | Sí: la traza no usa azar |
| Razonar el caso del usuario | No | Sí | Distribución, no relato | Sí: un `POST /chat` temperature 0 |
| Asunciones cuando falta un dato | Texto fijo | Puede omitirlas | Intervalo | El servicio añade “no personal context… default” |
| Reintento con el mismo `X-Request-ID` | N/A | Otro texto | Otra muestra | Devuelve el documento guardado y no vuelve a llamar al modelo |

Temperature 0 no hace el modelo una función pura entre procesos, por eso el
`correlation_id` único es el contrato de reintento. Un JSON inválido se
reintenta **una** vez; el segundo fallo es **502** y no se persiste. Un
5xx o un timeout del LLM es **502** / **504** y tampoco se persiste. No hay
éxito “solo con plantilla”.

Familias del árbol: sueño (default 7 h), tiempo (3 h de reuniones / 4 h de
foco), dinero (gasto 0 = desconocido) y salud (0 prescripciones). Tres
hojas obligatorias (optimistic, baseline, pessimistic) y hasta dos extras
si hay más de una familia. Tope: 5.

---

## Patrones y SOLID

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| Decision tree | `engine.py` | Elegir hojas y `trace` |
| Interpreter | `llm_client.py` → `POST /chat` | Redactar cada hoja con el contexto del usuario |
| Facade | API Router | El cliente no llama al puerto 8007 |
| Protocol (MCP) | `simulate_whatif` | Mismo contrato HTTP que `rag_search` |
| Idempotent command | índice único `correlation_id` | Reintento seguro |
| Gateway routing | premium vs free en el Router | El free ni siquiera llega al simulador |
| Anti-corruption | cliente RAG | Chroma y GridFS no entran al árbol |

| Principio | Aplicación |
|-----------|------------|
| **S** | El árbol elige; el cliente LLM razona; el cliente RAG hidrata; el repositorio persiste |
| **O** | Una familia nueva no cambia las rutas FastAPI |
| **L** | Body, RAG o default producen el mismo diccionario de variables |
| **I** | `POST /simulate`, `GET /simulations` y la herramienta MCP son contratos distintos |
| **D** | El motor depende de URLs, no de los pesos de Qwen ni de Chroma |

Kafka no entra: un hop de inferencia cabe en el presupuesto síncrono del
chat (30 s). El Router no publica `session.turn.completed` en simulate.

---

## Logging estructurado

Formato (`CorrelationFilter`):

```
%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s
```

Si falta `X-Request-ID`, el servicio genera un UUID, lo usa en RAG y en el
LLM, y lo devuelve en la respuesta.

### POST /simulate (variables completas: no hay RAG)

```
2026-09-21T15:02:00 [cid-1] INFO simulator-service: POST /simulate
2026-09-21T15:02:00 [cid-1] INFO simulator-service: POST /simulate user_id=user1 tier=premium
2026-09-21T15:02:00 [cid-1] INFO simulator-service: RAG hydrate skipped — client variables cover detected families
2026-09-21T15:02:00 [cid-1] INFO simulator-service: decision tree leaves=['optimistic', 'baseline', 'pessimistic'] count=3
2026-09-21T15:02:00 [cid-1] INFO simulator-service: LLM POST /chat http://llm-service:8003/chat temperature=0 model=Qwen3.5-4B
2026-09-21T15:02:01 [cid-1] INFO simulator-service: persisted simulation id=8f2c correlation_id=cid-1
```

### RAG hydrate

Con documentos:

```
2026-09-21T15:03:00 [cid-rag] INFO simulator-service: RAG hydrate → GET http://rag-service:8002/search user_id=user1
2026-09-21T15:03:00 [cid-rag] INFO simulator-service: RAG hydrate returned 1 hits
```

Sin hits (se aplican defaults y la asunción “No personal context was found…”):

```
2026-09-21T15:03:10 [cid-empty] INFO simulator-service: RAG hydrate → GET http://rag-service:8002/search user_id=user1
2026-09-21T15:03:10 [cid-empty] INFO simulator-service: RAG hydrate empty — applying defaults
```

RAG caído (no hay `persisted simulation`):

```
2026-09-21T15:03:20 [cid-rag-down] ERROR simulator-service: RAG hydrate HTTP 500
```

### LLM POST /chat

JSON inválido, un reintento, luego 502:

```
2026-09-21T15:04:00 [cid-json] WARNING simulator-service: LLM JSON invalid — retry 1
2026-09-21T15:04:00 [cid-json] WARNING simulator-service: LLM JSON invalid — retry 2
2026-09-21T15:04:00 [cid-json] ERROR simulator-service: LLM JSON invalid after retry
```

LLM 500 (sin persistir):

```
2026-09-21T15:04:10 [cid-fail] ERROR simulator-service: LLM service HTTP 500
```

Mismo `X-Request-ID` (no hay segundo `POST /chat`):

```
2026-09-21T15:04:20 [cid-same] INFO simulator-service: correlation_id hit — returning stored simulation
```

### GET /simulations

```
2026-09-21T15:05:00 [cid-list] INFO simulator-service: GET /simulations
2026-09-21T15:05:00 [cid-list] INFO simulator-service: GET /simulations user_id=user1
2026-09-21T15:05:01 [cid-one] INFO simulator-service: GET /simulations/8f2c
2026-09-21T15:05:01 [cid-one] INFO simulator-service: GET /simulations/8f2c user_id=user1
```

Un id de otro usuario responde **404** sin decir que el recurso existe.

### API Router

The first line is the correlation middleware (`POST /api/simulate`). The handler logs the same path again, then the token and the downstream call:

```
2026-09-21T15:06:00 [cid-sim] INFO api-gateway: POST /api/simulate
2026-09-21T15:06:00 [cid-sim] INFO api-gateway: POST /api/simulate
2026-09-21T15:06:00 [cid-sim] INFO api-gateway: JWT validated: user_id=user1, tier=premium
2026-09-21T15:06:00 [cid-sim] INFO api-gateway: Calling Simulator Service POST /simulate
```

Free → **403** antes de llamar al simulador. Sin JWT → **401**. La petición
11 del minuto → **429**. Ninguna de esas ramas publica Kafka.

### MCP simulate_whatif

```
2026-09-21T15:07:00 [cid-sim] INFO agents-service: POST /mcp/tools/simulate_whatif
2026-09-21T15:07:00 [cid-sim] INFO agents-service: MCP simulate_whatif → Simulator http://simulator-service:8007/simulate
```

Si el simulador responde 5xx, Agents registra el correlation id y devuelve
**502** o **504**. No inventa escenarios. Un nombre de herramienta
desconocido sigue siendo **404**. `reason_graph` y `learn_graph` no se
modifican.
