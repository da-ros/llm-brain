## Proposal: Decision-Support Simulator

### Context

Users need a decision-support tool that runs deterministic what-if scenarios based
on their personal data. The simulator generates 3-5 scenarios with explicit,
traceable assumptions to help users make informed decisions.

### Why

1. **Decision support**: The core value proposition — helping users make better
   decisions based on their personal knowledge.
2. **Thesis OE6**: Anteproyecto specifies deterministic what-if analysis with
   3-5 scenarios and explicit traceable assumptions.
3. **Trust**: Deterministic (not stochastic) simulations build user trust in
   the system's recommendations.

### Deliverables

- What-if scenario generator
- 3-5 scenarios per query with explicit assumptions
- Deterministic execution (same input -> same output)
- Assumption tracing (each assumption linked to source data)
- Scenario comparison view (web dashboard)
- Integration with RAG for context retrieval

### Non-Deliverables

- Monte Carlo / stochastic simulations
- Real-time market data integration
- Automated decision execution

### References

- Anteproyecto: Objetivo Específico 6 (Decision support)
- Depends on: Frame 1 (Architecture), Frame 3 (Hybrid Store + RAG)
- Parallel with: Frame 8 (Privacy & Scam Shield)
