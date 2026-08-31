## Context

The Decision-Support Simulator provides deterministic what-if analysis based on
the user's personal data. It generates multiple scenarios with explicit assumptions
that are traceable back to source documents.

## Goals / Non-Goals

**Goals:**
- Generate 3-5 scenarios per query
- Deterministic execution (reproducible results)
- Explicit assumptions linked to source documents
- Scenario comparison and ranking
- Integration with RAG for context retrieval

**Non-Goals:**
- Monte Carlo / stochastic simulations
- Real-time market data
- Automated decision execution

## Architecture Decisions

### 1. Simulation Type: Deterministic Rule-Based

**Decision**: Deterministic rule-based simulation (not Monte Carlo).

**Rationale**:
- Thesis specifies deterministic (not stochastic)
- Reproducible results build trust
- Simpler implementation, easier to validate
- Assumptions are explicit and auditable

### 2. Scenario Generation: LLM-Assisted

**Decision**: Use LLM to generate scenarios based on retrieved context.

**Rationale**:
- LLM excels at generating plausible scenarios
- Context from RAG ensures relevance to user data
- Assumptions extracted from LLM reasoning

### 3. Assumption Tracing: Document Links

**Decision**: Each assumption includes a reference to the source document.

**Rationale**:
- Transparency: user can verify assumptions
- Auditability: defense artifact for thesis
- Trust: user sees where recommendations come from

### 4. Scenario Format: Structured JSON

**Decision**: Scenarios output as structured JSON with fields: name, description,
assumptions[], outcome, confidence, source_docs[].

**Rationale**:
- Easy to render in web dashboard
- Machine-readable for comparison logic
- Human-readable for debugging

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| LLM generates unrealistic scenarios | Constraint prompts, validate against known patterns |
| Too many assumptions overwhelm users | Limit to 3-5 assumptions per scenario |
| Deterministic output feels rigid | Add "variation" parameter for slight randomization |
| Slow scenario generation | Cache common scenarios, async generation |

## Decisions Made

- Max scenarios per query: 5 (configurable)
- Max assumptions per scenario: 3
- Confidence score: 0.0 - 1.0 (LLM-assessed)
- Scenario output: `{name, description, assumptions[], outcome, confidence, source_docs[]}`
- Integration: POST /api/simulate with query + context
