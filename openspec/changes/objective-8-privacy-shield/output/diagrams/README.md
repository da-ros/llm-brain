# Frame 8 — Privacy Shield diagrams

Solid arrow: call or write. Arrowhead on the callee. `startArrow=none`, `endArrow=classic`.

Dashed arrow: HTTP response. Arrowhead on the caller.

Blue = Frame 1.1 / 3 / 4 / 5. Green = Shield. Yellow = RAG `POST /embed`.

The red note has no edges.

## shield-architecture.drawio

| From | To | Line | Meaning |
|------|----|------|---------|
| Client | API Router | solid | scan, incidents, guidelines |
| API Router | Client | dashed | 200 to the client |
| API Router | Shield | solid | `POST /scan` |
| Shield | API Router | dashed | 200 alert + reasons |
| Agents | Shield | solid | MCP, skips the Router |
| Shield | `POST /embed` | solid | query vector, not stored |
| `POST /embed` | Shield | dashed | 2048-d, not stored |
| Shield | LLM | solid | `POST /chat`, temperature 0 |
| LLM | Shield | dashed | likelihood and alert |
| Shield | MongoDB | solid | only when alert is true |

No edge from the client to port 8009. No edge into Chroma or Kafka. The blue RAG box is the service; the only RAG arrow lands on the yellow endpoint.

## shield-dataflow.drawio

Image path, left to right: Client → Router → Shield → OCR → Heuristics → Embed → LLM.

| From | To | Line | Meaning |
|------|----|------|---------|
| Client | Router | solid | submit |
| Router | Shield | solid | premium |
| Shield | OCR | solid | image |
| OCR | Heuristics | solid | OCR text |
| Heuristics | Embed | solid | rule ids |
| Embed | LLM | solid | nearest score |
| LLM | incidents | solid | only if alert |
| LLM | Router | dashed, above | 200 verdict |
| Router | Client | dashed | popup if alert |
| Shield | Embed | solid, under OCR | video, no OCR |
| Router | Client | dashed, red | 403 free, stops here |
| LLM | Router | dashed, red, below | 502/504, nothing stored |
| scan_message | Shield | solid | MCP. Does not go through the Router |

`No Kafka` is a label. It has no edge.
