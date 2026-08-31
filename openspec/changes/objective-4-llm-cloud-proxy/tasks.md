## Tasks

### A. Provider Protocol

- [ ] A.1 Define `LLMProvider` protocol in `apps/api/llm/base.py`
      — chat(messages, context) -> str, complete(prompt) -> str
- [ ] A.2 Define `ProviderConfig` dataclass: model, api_key, max_tokens, temperature

### B. Cloud Provider (AWS Bedrock)

- [ ] B.1 Implement `BedrockProvider` in `apps/api/llm/bedrock.py`
      — Uses boto3 for Bedrock invocation
- [ ] B.2 Implement chat() with streaming support
- [ ] B.3 Add error handling: throttling, model not found, invalid input
- [ ] B.4 Add cost tracking: tokens used per request

### C. Local Provider (llama.rn)

- [ ] C.1 Implement `LocalProvider` in `apps/api/llm/local.py`
      — llama.rn binding for on-device inference
- [ ] C.2 Implement model download and caching
- [ ] C.3 Implement chat() with token count and speed metrics
- [ ] C.4 Add model management: load(), unload(), get_status()

### D. Provider Resolver

- [ ] D.1 Implement `get_provider(tier)` in `apps/api/llm/resolver.py`
      — Selects provider by subscription tier (free -> local, premium -> bedrock)
- [ ] D.2 Add startup validation: verify provider availability
- [ ] D.3 Add graceful fallback: if cloud unavailable, fallback to local (with warning)

### E. Fine-Tuning Pipeline

- [ ] E.1 Implement dataset preparation: triples -> Bedrock training format
- [ ] E.2 Implement LoRA fine-tuning job submission to AWS Bedrock
- [ ] E.3 Implement training status polling and completion notification
- [ ] E.4 Add training log: dataset, hyperparams, metrics, model version

### F. Testing

- [ ] F.1 Unit tests for LLMProvider protocol (mock implementations)
- [ ] F.2 Unit tests for provider resolver (tier switching)
- [ ] F.3 Integration test: BedrockProvider chat (with real or mocked API)
- [ ] F.4 Integration test: LocalProvider inference (with small test model)
- [ ] F.5 End-to-end test: upload -> distill -> embed -> chat with context
