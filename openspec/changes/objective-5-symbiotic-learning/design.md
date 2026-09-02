## Context

The symbiotic learning loop is the mechanism by which the platform improves over
time. Three MCP agents work together: Ingestor processes raw interactions into
training data, Razonador generates contextual suggestions, and Evaluador scores
quality to decide when fine-tuning is triggered.

## Goals / Non-Goals

**Goals:**
- Implement Ingestor agent (interaction -> training data)
- Implement Razonador agent (context -> suggestions)
- Implement Evaluador agent (quality scoring -> fine-tuning trigger)
- Manual incremental fine-tuning batch system
- Agent communication via structured messages

**Non-Goals:**
- Autonomous retraining (manual trigger only)
- RLHF (reinforcement learning from human feedback)
- Multi-agent debate/consensus

## Architecture Decisions

### 1. Agent Framework: Custom MCP-like Agents

**Decision**: Lightweight custom agent framework following MCP patterns.

**Rationale**:
- MCP is emerging standard for agent communication
- Custom implementation keeps dependencies minimal
- Easy to extend with new agent types

### 2. Agent Communication: Structured Messages

**Decision**: Agents communicate via typed message objects.

**Rationale**:
- Clear input/output contracts
- Easy to log and debug
- Enables agent composition

### 3. Fine-Tuning Trigger: Evaluador Threshold

**Decision**: Fine-tuning triggered when Evaluador scores drop below threshold.

**Rationale**:
- Prevents unnecessary fine-tuning (cost/latency)
- Quality-driven (not time-driven)
- Manual override available

### 4. Training Data: Interaction Logs

**Decision**: Use user interaction logs (queries, responses, feedback) as training data.

**Rationale**:
- Real user data improves relevance
- Privacy-preserving (anonymized)
- Incremental batches (not full retraining)

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Agent latency on user queries | Run agents async, respond with cached results |
| Training data quality | Evaluador filters low-quality samples |
| Fine-tuning cost | Batch size limits, manual trigger, cost alerts |
| Privacy concerns | Anonymize training data, per-user isolation |

## Decisions Made

- Agent protocol: `process(input: AgentInput) -> AgentOutput`
- Ingestor output: `{interaction_id, user_id, query, response, context, timestamp}`
- Razonador output: `{suggestion, confidence, reasoning}`
- Evaluador output: `{score, should_finetune, reason}`
- Fine-tuning batch: collect N interactions, then trigger manual fine-tune
- Max batch size: 50 interactions (configurable)
