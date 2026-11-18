# Architecture — llm-brain

Frame 1 defense artifacts for Objetivo Específico 1.

| Path | What |
|------|------|
| [current-runtime.md](current-runtime.md) | How the system runs: host LLM, `llama.rn`, fine-tune, Fernet, CI |
| [decisions.md](decisions.md) | Earlier decisions and what the implementation does now |
| [project-architecture-overview.md](project-architecture-overview.md) | Service map, ports, and who calls the model |
| [stack.md](stack.md) | OSS stack + rationale |
| [security.md](security.md) | Shift Left (CI) and future Shift Right |
| [../../openspec/changes/objective-1-0-architecture-repo/output/diagrams/](../../openspec/changes/objective-1-0-architecture-repo/output/diagrams/) | C4, deployment, MCP diagrams |

Local MVP: clients call the API Router directly. The LLM and the fine-tune job are host processes on ports 8003 and 8004. AWS API Gateway, ECS Fargate, and Bedrock are future work, outside this MVP.
