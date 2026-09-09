# Frame 1.1 — API Router diagrams

Draw.io XML for the API Router (local MVP gateway). AWS API Gateway is future / out of scope.

## Files

| File | Description |
|------|-------------|
| `api-router-architecture.drawio` | Router internals: JWT, correlation ID, rate limit, routes, Kafka, MongoDB |
| `api-router-dataflow.drawio` | Upload (async Kafka), chat (sync HTTP), polling, retry / DLQ |

## Open

Draw.io Desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io Integration extension.

## Color scheme

Legend at the bottom of each diagram uses a colored dot (not the color name):

- Blue `#dae8fc` — clients
- Yellow `#fff2cc` — API Router (auth, correlation ID, rate limit)
- Green `#d5e8d4` — ETL / RAG / LLM
- Purple `#e1d5e7` (dashed) — AWS future
- Red `#f8cecc` — Kafka / DLQ
- Gray `#f5f5f5` — MongoDB (task_status + GridFS)

## References

- [C4 Model](https://c4model.com/)
- [Frame 1 diagrams](../../objective-1-0-architecture-repo/output/diagrams/)
