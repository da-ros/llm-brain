# Frame 7 — User Interface diagrams

Solid arrow: call or write. Arrowhead on the callee. `startArrow=none`, `endArrow=classic`.

Dashed arrow: HTTP response. Arrowhead on the caller.

Blue = earlier frames (Router, RAG, LLM, Simulator, Agents). Green = this frame (the web app and Analytics). Yellow = Shield.

The red note has no edges.

## ui-architecture.drawio

The browser has one solid edge, into the API Router. There is no edge from the web app to port 8008 or to any other service.

| From | To | Line | Meaning |
|------|----|------|---------|
| Encefalus web | API Router | solid | every `/api` call |
| API Router | Encefalus web | dashed, left side | JSON for the screen |
| API Router | Analytics | solid, labeled Analytics | `/ingest`, `/correlations` |
| API Router | Simulator | solid, labeled Decisions | `/simulate` |
| API Router | Shield | solid, yellow, labeled Shield | `/scan`, `/incidents` |
| API Router | RAG | solid, labeled Memory | `/documents` |
| API Router | Agents | solid, labeled Brain · Learning | `/chat`, `/learning` |
| Agents | Analytics | solid, under the row | `analytics_query`. The browser does not take this hop |
| Analytics | RAG | solid | `GET /search` during ingest |
| Analytics | LLM | solid, labeled ingest | `POST /chat` |
| Analytics | MongoDB | solid, labeled snapshot | metrics and the narrative |

Home makes no call. Welcome calls only sign-up and sign-in.

## ui-dataflow.drawio

Top row: Welcome `POST /auth` → Router (JWT and plan) → Shell. Home makes no call.

Middle row: Screen → Router (plan check) → owning service → the screen renders the JSON. The last hop is dashed. The green box on the right lists the call for each screen. It has no edges.

A red edge drops from Screen to Premium notice on the free plan. That is Memory, Decisions, Analytics, Shield, and Learning.

Bottom row: a diary file (csv, xlsx, docx, ics, or image) → Ingest → Pearson. The middle hop is RAG plus the LLM. Pearson writes the snapshot down to MongoDB and sends `r`, `n`, and `points` to the scatter. A dashed red edge from Ingest to `502 · no write` is an LLM failure. That label has no outgoing edge.

No edge into Kafka. No edge to Google.
