# Tutor alignment — architecture scope (A.7)

**Change:** `objective-1-0-architecture-repo`  
**Tutor:** Ing. Rodolfo Bojorque, PhD · UPS  
**Authors:** Pedro David Rodas Mantilla, Giovanny Daniel Jácome Cajamarca

This package aligns Frame 1 with `openspec/input/context.txt` so later modules are not built on Bedrock/Atlas.

## Scope to confirm

1. Local MVP only. AWS API Gateway / ECS / Bedrock = future, not graded in this MVP.
2. One model family: Qwen3.5-4B (cloud container = **base**; on-device Free = **base Q4**; on-device Premium = **fine-tuned Q4**).
3. Multi-tenant JWT + bcrypt; data isolated by `user_id`.
4. Microservices: API Router 8000, ETL 8001, RAG 8002, LLM 8003, Fine-Tune 8004, Agents 8006, Chroma host 8005, Mongo 27017, Kafka 9092.
5. MCP agents (Ingestor / Razonador / Evaluador) are specified here and implemented in Frame 5.

## Artifacts for review

- `output/diagrams/*.drawio` (C4 L1–L3, deployment, MCP)
- `docs/architecture/decisions.md`, `stack.md`, `security.md`
- Runnable skeleton: `apps/api` (`GET /health`, JWT, `LLMProvider`)

## Status

Planning artifacts and implementation in this change now match the proposal/design/spec for the local Qwen topology. Formal sign-off remains with the tutor; this file is the alignment record used before later frames proceed.
