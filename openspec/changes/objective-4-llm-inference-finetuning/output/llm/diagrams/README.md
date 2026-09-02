# Diagrams — LLM Service

## llm-architecture.drawio

Architecture diagram showing:
- **API Router** (blue, existing) — upstream caller on port 8000
- **LLM Service** (green, new) — FastAPI app on port 8003
  - `POST /generate` — text completion
  - `POST /chat` — multi-turn chat
  - `GET /health` — provider status
  - Provider layer: LLMProvider Protocol → BedrockProvider → boto3
- **AWS Bedrock** (orange, external) — Llama 3 8B inference API
- **Config** — AWS credentials, Bedrock model ID

**Color convention**:
- Blue: Existing components from previous frames
- Green: New components in this frame
- Orange: External services (AWS Bedrock)

## llm-dataflow.drawio

Data flow diagram showing:
1. **Inference flow**: Client → API Router → LLM Service → Resolver → BedrockProvider → AWS Bedrock → Response
2. **Error paths**: Bedrock throttling (500), invalid tier (400), model not found (500), timeout (504), missing prompt (422)
3. **Key design notes**: asyncio.to_thread, per-request provider, stubbed Bedrock, correlation ID propagation
