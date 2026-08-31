## Context

The LLM provider layer abstracts the difference between cloud (premium) and
on-device (free) inference. It follows a protocol-based design so the rest of
the application is agnostic to the underlying model.

## Goals / Non-Goals

**Goals:**
- Define LLMProvider protocol for chat/completion
- Implement BedrockProvider (AWS Bedrock, Llama 3 8B)
- Implement LocalProvider (llama.rn, Llama 3.2 3B Q4_K_M)
- Provider resolver selects by subscription tier
- LoRA fine-tuning pipeline on AWS Bedrock
- On-device model management (download, load, inference)

**Non-Goals:**
- Training from scratch
- Custom model architectures
- Multi-model ensemble

## Architecture Decisions

### 1. Protocol: LLMProvider (Python Protocol)

**Decision**: Define LLMProvider as a Python Protocol (structural subtyping).

**Rationale**:
- No inheritance required (duck typing)
- Easy to mock for testing
- Clear interface: chat(), complete(), stream()

### 2. Cloud: AWS Bedrock (not OpenAI, not self-hosted)

**Decision**: AWS Bedrock for cloud inference and fine-tuning.

**Rationale**:
- Managed service, no infrastructure
- Free tier 750h/mes
- Native LoRA fine-tuning support
- Same provider for training and inference

### 3. On-Device: llama.rn (not ollama, not python binding)

**Decision**: llama.rn for mobile on-device inference.

**Rationale**:
- Native React Native bindings
- GGUF model format (quantized, efficient)
- 18-25 tok/s on modern phones
- Free tier requires no server

### 4. Fine-Tuning: LoRA on AWS Bedrock

**Decision**: LoRA (Low-Rank Adaptation) for fine-tuning Llama 3 8B.

**Rationale**:
- Parameter-efficient (trains <1% of weights)
- Lower compute cost than full fine-tuning
- AWS Bedrock managed workflow
- Preserves base model capabilities

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Bedrock cold start latency | Keep warm instances, async inference |
| llama.rn model download size (~2GB) | Lazy download, cache on device |
| LoRA training quality | Monitor loss curves, validate with test set |
| Provider switching mid-conversation | Stateless requests, no session dependency |

## Decisions Made

- Provider selection: `LLM_PROVIDER` env var + subscription tier
- Cloud model: Llama 3 8B (base) + LoRA adapter (fine-tuned)
- On-device model: Llama 3.2 3B Q4_K_M (quantized)
- Fine-tuning dataset: user triples from Frame 2
- Inference format: `{"prompt": "...", "context": "...", "response": "..."}`
