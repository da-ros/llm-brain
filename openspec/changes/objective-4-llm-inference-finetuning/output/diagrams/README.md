# Diagrams — LLM Cloud (Bedrock) + Fine-Tuning Services

## llm-architecture.drawio

Architecture diagram showing:
- LLM Service (port 8003) — inference for premium users
- Fine-Tune Service (port 8004) — LoRA training background worker
- AWS Bedrock integration (inference + fine-tuning)
- API Router connection (HTTP sync)

**Color convention**:
- Blue: Existing components from previous frames
- Green: New components in this frame
- Orange: External services (AWS Bedrock)

## llm-dataflow.drawio

Data flow diagram showing:
1. **Inference flow**: API Router → LLM Service → AWS Bedrock → Response
2. **Fine-tuning flow**: Trigger → Fine-Tune Service → Bedrock Training → LoRA Adapter
3. **Error paths**: Bedrock throttling, timeout, training failure

**Sequence**:
- Inference: synchronous (30s timeout)
- Fine-tuning: asynchronous (hours, polled via /status)
