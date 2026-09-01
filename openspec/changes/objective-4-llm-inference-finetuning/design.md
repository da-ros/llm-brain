## Design: LLM Cloud (Bedrock) + Fine-Tuning Services

### Architecture Overview

```
                    API Router (port 8000)
                           │
              ┌────────────┴────────────┐
              │ HTTP (sync)             │ Kafka (async)
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────────┐
│    LLM Service      │    │    Fine-Tune Service     │
│    Puerto 8003      │    │    Puerto 8004           │
│                     │    │                           │
│ POST /generate      │    │ POST /train               │
│ POST /chat          │    │ GET  /status/:job_id      │
│ GET  /health        │    │ GET  /health              │
└─────────┬───────────┘    └───────────┬───────────────┘
          │                            │
          ▼                            ▼
┌─────────────────────────────────────────────────────┐
│                   AWS Bedrock                        │
│                                                      │
│  ┌──────────────────┐    ┌────────────────────────┐  │
│  │   Inference       │    │   Fine-Tuning (LoRA)   │  │
│  │   Llama 3 8B      │    │   Llama 3 8B + LoRA    │  │
│  └──────────────────┘    └────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Components

#### 1. LLM Service (`services/llm/`)

**Responsibility**: Receive inference requests from API Router, call AWS Bedrock, return responses.

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/generate` | POST | Text completion | `{"prompt": "...", "user_id": "..."}` | `{"response": "...", "tokens_used": N}` |
| `/chat` | POST | Chat with context | `{"messages": [...], "context": "...", "user_id": "..."}` | `{"response": "...", "tokens_used": N}` |
| `/health` | GET | Provider status | — | `{"status": "ok", "provider": "bedrock", "model": "..."}` |

**Provider Layer**:
```
providers/
├── base.py         ← LLMProvider Protocol
├── bedrock.py      ← BedrockProvider (AWS Bedrock, Llama 3 8B)
└── resolver.py     ← get_provider() — selects by tier
```

**Key Design Decisions**:

1. **Protocol-based design** (Python Protocol, not ABC):
   - Structural subtyping — no inheritance required
   - Easy to mock for testing
   - Clear interface: `chat()`, `complete()`

2. **AWS Bedrock** (not OpenAI, not self-hosted):
   - Managed service, no infrastructure
   - Free tier 750h/month
   - Native LoRA fine-tuning support
   - Same provider for training and inference

3. **Stateless requests**:
   - No session management between requests
   - Each request is independent
   - Provider selected per-request by tier

#### 2. Fine-Tune Service (`services/finetune/`)

**Responsibility**: Manage LoRA fine-tuning jobs on AWS Bedrock.

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/train` | POST | Submit training job | `{"user_id": "...", "dataset_path": "..."}` | `{"job_id": "...", "status": "submitted"}` |
| `/status/:job_id` | GET | Get training status | — | `{"job_id": "...", "status": "...", "metrics": {...}}` |
| `/health` | GET | Service status | — | `{"status": "ok"}` |

**Training Pipeline**:
```
Triples (JSONL) → Format conversion → Bedrock training job → LoRA adapter → Model version
```

**Key Design Decisions**:

1. **LoRA** (Low-Rank Adaptation):
   - Parameter-efficient (<1% of weights trained)
   - Lower compute cost than full fine-tuning
   - Preserves base model capabilities

2. **Background worker**:
   - Training jobs run asynchronously
   - Status polled via `/status/:job_id`
   - Training can take hours — not blocking

3. **Dataset from Frame 2**:
   - Input: triples extracted by ETL service
   - Format: convert triples to Bedrock training format
   - Triggered by agent or manual trigger (not automatic)

### Configuration

**LLM Service** (`services/llm/config.py`):
```python
# AWS Bedrock
AWS_ACCESS_KEY_ID: str
AWS_SECRET_ACCESS_KEY: str
AWS_REGION: str = "us-east-1"
BEDROCK_MODEL_ID: str = "meta.llama3-8b-instruct-v1:0"

# Service
LLM_HOST: str = "0.0.0.0"
LLM_PORT: int = 8003
```

**Fine-Tune Service** (`services/finetune/config.py`):
```python
# AWS Bedrock
AWS_ACCESS_KEY_ID: str
AWS_SECRET_ACCESS_KEY: str
AWS_REGION: str = "us-east-1"
BEDROCK_MODEL_ID: str = "meta.llama3-8b-instruct-v1:0"

# Training
TRAINING_EPOCHS: int = 5
TRAINING_LR: float = 0.001
MAX_TRAINING_TIME_HOURS: int = 2

# Service
FINETUNE_HOST: str = "0.0.0.0"
FINETUNE_PORT: int = 8004
```

### Communication with API Router

The API Router (`services/api-router/`) already calls:
```python
# In services/api-router/routers/chat.py
async with httpx.AsyncClient(timeout=30.0) as client:
    llm_response = await client.post(
        "http://llm-service:8003/generate",
        json={"prompt": prompt, "user_id": user_id, "tier": tier},
        headers={"X-Request-ID": correlation_id},
    )
```

This integration is already in place — the LLM Service just needs to respond on port 8003.

### Migration from Monolith

| Monolith file | Destination | Notes |
|---------------|-------------|-------|
| `services/api/llm/base.py` | `services/llm/providers/base.py` | Protocol — no changes |
| `services/api/llm/bedrock.py` | `services/llm/providers/bedrock.py` | Provider — no changes |
| `services/api/llm/resolver.py` | `services/llm/providers/resolver.py` | Resolver — update imports |
| `services/api/config.py` (LLM部分) | `services/llm/config.py` | Extract LLM-related config |

After Frame 4 is complete and tested, `services/api/` (monolith) is deleted.

### Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Bedrock cold start latency | Keep warm instances, async inference |
| LoRA training quality | Monitor loss curves, validate with test set |
| AWS cost | Free tier 750h/month, monitor usage |
| Provider switching | Stateless requests, no session dependency |
