# Architecture — llm-brain

Frame 1 defense artifacts for Objetivo Específico 1.

| Path | What |
|------|------|
| [decisions.md](decisions.md) | Deviations and architecture decisions vs the original sketch |
| [project-architecture-overview.md](project-architecture-overview.md) | Running microservice map (ports 8000–8004, Frame 4 LLM + LoRA) |
| [stack.md](stack.md) | OSS stack + rationale |
| [security.md](security.md) | Shift Left (CI) and future Shift Right |
| [../openspec/changes/objective-1-0-architecture-repo/output/diagrams/](../openspec/changes/objective-1-0-architecture-repo/output/diagrams/) | C4, deployment, MCP diagrams |

Local MVP: clients → API Router directly. AWS API Gateway / ECS Fargate / Bedrock are **future, out of scope**.
