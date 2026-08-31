## Proposal: LLM Cloud Fine-Tune + On-Device

### Context

The platform needs two LLM execution modes: cloud-based fine-tuned models (premium)
via AWS Bedrock, and on-device inference (free) via llama.rn. This frame implements
the LLM provider abstraction layer and both provider implementations.

### Why

1. **Dual-tier execution**: Free users get on-device LLM, premium users get cloud
   fine-tuned models — the provider layer abstracts this difference.
2. **Thesis OE4**: Anteproyecto specifies LoRA fine-tuning on AWS Bedrock (Llama 3 8B)
   and on-device inference (llama.rn, Llama 3.2 3B Q4_K_M).
3. **Model agnostic**: The provider protocol allows switching models without code changes.

### Deliverables

- LLMProvider protocol (chat/completion interface)
- BedrockProvider implementation (AWS Bedrock, Llama 3 8B)
- LocalProvider implementation (llama.rn, Llama 3.2 3B Q4_K_M)
- Provider resolver: `get_provider(tier)` selects by subscription tier
- LoRA fine-tuning pipeline on AWS Bedrock
- On-device model loading and inference

### Non-Deliverables

- Model training from scratch
- Custom model architectures
- Multi-model ensemble

### References

- Anteproyecto: Objetivo Específico 4 (LLM principal)
- Depends on: Frame 2 (Memory Distillation)
