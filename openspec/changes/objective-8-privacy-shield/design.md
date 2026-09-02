## Context

The Privacy & Scam Shield analyzes user documents for phishing attempts, scam
patterns, and privacy leaks. It uses a combination of rule-based heuristics
and embedding similarity to detect threats and alert users.

## Goals / Non-Goals

**Goals:**
- Detect phishing patterns via heuristics (keywords, URLs, urgency signals)
- Detect scam patterns via embedding similarity (compare against known scams)
- Detect privacy leaks (SSN, credit card, phone number patterns)
- Alert system for detected threats
- Integration with document upload pipeline

**Non-Goals:**
- Real-time email scanning
- External threat intelligence feeds
- Automated document quarantine
- Full-scale fraud detection ML models

## Architecture Decisions

### 1. Detection Strategy: Hybrid (Heuristics + Embeddings)

**Decision**: Combine rule-based heuristics with embedding similarity.

**Rationale**:
- Heuristics: fast, interpretable, catches known patterns
- Embeddings: catches novel variants, semantic similarity
- Hybrid: best coverage with reasonable complexity

### 2. Heuristics: Regex + Keyword Matching

**Decision**: Use regex patterns and keyword lists for rule-based detection.

**Rationale**:
- Fast execution (no ML inference needed)
- Interpretable (user can understand why flagged)
- Easy to update (add new patterns without retraining)

### 3. Embeddings: Compare Against Known Scam Database

**Decision**: Maintain a small database of known scam patterns as embeddings.

**Rationale**:
- Catch variations of known scams
- Semantic similarity catches paraphrased threats
- Small database (low storage cost)

### 4. Alerts: In-App Notifications

**Decision**: Show alerts in the web/mobile app (not email/SMS).

**Rationale**:
- Simple implementation
- No external service dependency
- User can review and dismiss alerts

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| False positives annoy users | Confidence threshold, allow user dismissal |
| Heuristics miss novel scams | Embedding similarity catches variations |
| Privacy leak detection accuracy | Pattern-based (not ML), conservative matching |
| Performance on large documents | Process async, cache results |

## Decisions Made

- Alert severity: low, medium, high, critical
- Heuristic patterns: SSN, credit card, phone, email, urgency keywords
- Embedding threshold: cosine similarity > 0.8 = match
- Alert storage: MongoDB with user_id isolation
- Integration: post-upload hook, on-demand scan endpoint
