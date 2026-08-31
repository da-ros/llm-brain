## Proposal: Alpha Validation + KPIs + Demo

### Context

The final frame validates the entire platform through automated tests, integration
tests, KPI measurement (latency, RAG precision), and a video demo for the thesis
defense.

### Why

1. **Thesis defense**: The alpha validation provides evidence that the system works
   as designed and meets performance targets.
2. **Thesis OE9**: Anteproyecto specifies pytest, FastAPI+Mongo integration tests,
   KPIs (mean latency, RAG Top-3 precision), and video demo.
3. **Quality gate**: Ensures the MVP is functional before thesis submission.

### Deliverables

- pytest test suite (unit + integration)
- FastAPI + MongoDB integration tests
- KPI measurement: mean latency, RAG Top-3 precision
- Performance benchmarks (response times, throughput)
- Video demo (5-10 minutes) for thesis defense
- Architecture validation against C4 diagrams

### Non-Deliverables

- Load testing / stress testing
- Security penetration testing
- Production deployment
- User acceptance testing

### References

- Anteproyecto: Objetivo Específico 9 (Validation)
- Depends on: ALL previous frames (F1-F8, F10)
- Terminal frame: last to execute
