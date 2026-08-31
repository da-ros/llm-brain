## Proposal: Privacy & Scam Shield

### Context

Users need protection against phishing, scams, and privacy leaks in their personal
documents. The shield analyzes content using heuristics and embedding similarity
to detect suspicious patterns and alert users.

### Why

1. **User safety**: Personal documents may contain sensitive data that could be
   exploited by scammers or phishing attempts.
2. **Thesis OE8**: Anteproyecto specifies phishing/scam detection via heuristics
   + embedding similarity with alert system.
3. **Trust**: Users share personal medical, financial data — security is critical.

### Deliverables

- Phishing/scam detection via heuristics (keyword patterns, URL analysis)
- Embedding similarity detection (compare against known scam patterns)
- Alert system (in-app notifications for detected threats)
- Privacy leak detection (SSN, credit card, phone number patterns)
- Integration with document upload pipeline

### Non-Deliverables

- Real-time email scanning
- External threat intelligence feeds
- Automated document quarantine
- Full-scale fraud detection ML models

### References

- Anteproyecto: Objetivo Específico 8 (Privacy shield)
- Depends on: Frame 1 (Architecture), Frame 3 (Hybrid Store + RAG)
- Parallel with: Frame 6 (Decision Support)
