## Proposal: Symbiotic Learning Loop (MCP Agents)

### Context

The platform uses MCP (Model Context Protocol) agents to create a learning loop
where the system continuously improves from user interactions. Three agents
(Ingestor, Razonador, Evaluador) process user data, reason over it, and evaluate
output quality to trigger incremental fine-tuning.

### Why

1. **Continuous improvement**: The system should get better over time from user
   interactions — this is the "symbiotic" aspect of Brain-LLM symbiosis.
2. **Thesis OE5**: Anteproyecto specifies MCP agents for the learning loop
   with manual incremental fine-tuning batches.
3. **Feedback loop**: User corrections and preferences should influence model
   behavior through fine-tuning.

### Deliverables

- MCP agent framework (Ingestor, Razonador, Evaluador)
- Ingestor: processes user interactions into training data
- Razonador: reasons over user context and generates suggestions
- Evaluador: scores output quality, triggers fine-tuning when threshold met
- Manual incremental fine-tuning batch system
- Agent communication protocol

### Non-Deliverables

- Autonomous retraining (manual trigger only)
- Reinforcement learning from human feedback (RLHF)
- Multi-agent debate/consensus

### References

- Anteproyecto: Objetivo Específico 5 (Learning loop)
- Depends on: Frame 2 (Memory Distillation), Frame 3 (Hybrid Store), Frame 4 (LLM Provider)
