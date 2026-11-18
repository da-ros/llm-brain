# Project architecture overview

Source of truth: `openspec/input/context.txt`. Running details:
[current-runtime.md](current-runtime.md).

## Local MVP

"Cloud" means the Qwen process on the Mac, not a container and not AWS.

| Service | Port | Where | Role |
|---------|------|--------|------|
| API Router | 8000 | Compose | JWT, Kafka upload, sync chat, model-pack download |
| ETL | 8001 | Compose | One-tap distillation to triples JSONL |
| RAG | 8002 | Compose | Mongo metadata, Chroma retrieval, Fernet on chunk text |
| LLM | 8003 | Host process | Base Qwen3.5-4B. Web free, web premium, and ETL extraction |
| Fine-tune | 8004 | Host process | Manual LoRA. Compose builds the image and does not publish this port |
| Chroma | 8005 | Compose | Vector index. Container port 8000 |
| Agents | 8006 | Compose | `reason_graph` and `learn_graph` |
| Simulator | 8007 | Compose | Decision-support what-if |
| Analytics | 8008 | Compose | Pearson correlations |
| Shield | 8009 | Compose | Phishing and scam scan |
| Web | 3080 → 3000 | Compose | TanStack Start. The browser uses 3080 |
| MongoDB | 27017 | Compose | Users, documents, GridFS |
| Kafka | 9092 | Compose | `file.uploaded`, `session.turn.completed` |

The API Router, ETL, agents, simulator, shield, and analytics call the LLM at
`http://host.docker.internal:8003`. The router and the agents call fine-tune
at `http://host.docker.internal:8004`. There is no `http://llm-service:8003`
route in Compose.

## Who calls the model

- Web free chat calls port 8003 directly. RAG and `learn_graph` are skipped.
- Web premium chat calls the agents service. `reason_graph` retrieves, then
  calls port 8003. After HTTP 200, Kafka starts `learn_graph`.
- Phone free and phone premium "On device" load a GGUF pack with `llama.rn`.
  They do not call port 8003.
- Phone premium "Digital Brain" uses the same premium web chat path.

## Frame 4 boundary

The LoRA adapter is written for the premium on-device pack. Nothing in the
fine-tune job reloads the weights of the process on port 8003. ETL extraction
uses `POST /extract` on that same base model.

AWS Bedrock and Llama are out of scope.
