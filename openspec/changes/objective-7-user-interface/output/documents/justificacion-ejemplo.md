# Justificación — User Interface (Frame 7)

El Frame 7 es la interfaz de Encefalus (`apps/web`). La persona entra por
la pantalla de bienvenida, crea una cuenta o inicia sesión, y el shell
abre Home. Cada pantalla de producto se llena con la respuesta del API
Router. El navegador no llama a un puerto de servicio y no recalcula lo
que el servicio ya guardó.

El anteproyecto nombra este objetivo Life Analytics. Ese tablero es la
pantalla **Analytics** dentro de esta interfaz. El resto del frame es el
producto: Brain, Memory, Decisions, Shield, Learning y Settings.

## Una fachada

| Pantalla | Plan | De dónde sale lo que se ve |
|----------|------|----------------------------|
| Welcome | ninguno | `POST /api/auth/signup`, `POST /api/auth/signin` |
| Home | ambos | no llama al API |
| Brain | ambos | chats, turnos y `POST /api/chat` |
| Memory | premium | documentos y `POST /api/upload` |
| Decisions | premium | `GET /api/simulations`, `POST /api/simulate` |
| Analytics | premium | correlaciones, métricas e ingest |
| Shield | premium | incidentes y `POST /api/shield/scan` |
| Learning | premium | `GET /api/learning`, `POST /api/finetune` |
| Settings | ambos | cuenta, seis servicios, almacenamiento |

Una cuenta nueva es free. En free, Brain no usa RAG y no guarda los
archivos como memoria. Hasta cinco archivos van en la pregunta y se
reenvían con las preguntas siguientes de ese chat. Memory, Decisions,
Analytics, Shield y Learning muestran que esas pantallas son del plan
Premium. El router responde 403 si el token free llama a esos módulos.

No hay inicio de sesión con Apple ni con Google. No hay OAuth de
calendario. Un diario o un horario en Analytics es un archivo.

## Analytics no se calcula en el navegador

La pantalla dibuja dos dispersiones: sueño contra productividad, y
reuniones contra foco. `r`, `n` y el `narrative` llegan en
`GET /api/analytics/correlations`. Si el par viene `insufficient`, la
pantalla lo dice y no inventa un `r`.

El cálculo sigue en el Analytics Service (puerto 8008), después de que
Qwen3.5-4B infiere los días:

```
r = Σ(x − x̄)(y − ȳ) / sqrt(Σ(x − x̄)² · Σ(y − ȳ)²)
```

| | Monte Carlo | Pearson |
|--|-------------|---------|
| Alcance del MVP | Fuera | Sí |
| Mismos puntos | Otro r | El mismo r, 4 decimales |
| n &lt; 2 o varianza cero | Un intervalo inventado | `r: null`, `status: insufficient` |

Un archivo vacío es 422 y no llama al modelo. Si el modelo falla, la
respuesta es 502/504 y no se escribe `life_metrics` ni
`analytics_snapshots`. El MCP `analytics_query` existe para Agents. La
interfaz no lo llama.

## Patrones y SOLID

| Patrón | Dónde | Para qué |
|--------|-------|----------|
| Facade | API Router | El navegador no llama al puerto 8008 |
| Gate | Welcome y el aviso Premium | Sin token no hay producto; free no ve datos premium |
| Snapshot | `analytics_snapshots` | El `r` de la pantalla es el `r` guardado |

| Principio | Aplicación |
|-----------|------------|
| S | Cada pantalla pinta un módulo. Pearson y el LLM quedan en Analytics |
| O | Una pantalla nueva es una ruta. Un par nuevo sigue usando `points`, `r`, `n` |
| I | La pantalla llama la ruta que muestra. No usa el contrato MCP |
| D | La web depende del JSON del router |

`reason_graph` no cambia. No hay Kafka en el camino de la pantalla.

## Logs

```
2026-10-01T00:12:04 [cid-ui] INFO api-gateway: POST /api/auth/signin
2026-10-01T00:12:11 [cid-ui] INFO api-gateway: GET /api/analytics/correlations user_id=user1
2026-10-01T00:12:11 [cid-ui] INFO api-gateway: GET analytics-service:8008/correlations
2026-10-01T00:14:02 [cid-analytics] INFO analytics-service: POST /ingest user_id=user1 filename=diary.csv
2026-10-01T00:14:03 [cid-analytics] INFO analytics-service: LLM POST /chat http://host.docker.internal:8003/chat temperature=0 model=Qwen3.5-4B
2026-10-01T00:14:04 [cid-analytics] INFO analytics-service: snapshot id=snap-1 rows_upserted=2
```

`CorrelationFilter` añade `correlation_id` a cada línea del servicio. El
mismo id sale hacia RAG y hacia el LLM. La pantalla solo recibe el JSON.
