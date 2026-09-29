## Design: LLM Inference (local Qwen3.5-4B container) + Fine-Tuning Services

### Architecture Overview

```
                    API Router (port 8000)
                           │
              ┌────────────┴────────────┐
              │ HTTP (sync)             │ HTTP (manual trigger)
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
│         Local Docker (laptop) — "cloud"              │
│                                                      │
│  ┌──────────────────┐    ┌────────────────────────┐  │
│  │   Inference       │    │   Fine-Tuning (LoRA)   │  │
│  │  Qwen3.5-4B       │    │  Qwen3.5-4B + LoRA     │  │
│  │  (container)      │    │  (PEFT/ms-swift/Unsloth│  │
│  └──────────────────┘    └────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Components

#### 1. LLM Service (`services/llm/`)

**Responsibility**: Receive multimodal inference requests from API Router, run Qwen3.5-4B in the local container, return responses.

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/generate` | POST | Text completion | `{"prompt": "...", "user_id": "..."}` | `{"response": "...", "tokens_used": N}` |
| `/chat` | POST | Multimodal chat with context (text/image/video) | `{"messages": [...], "context": "...", "user_id": "..."}` | `{"response": "...", "tokens_used": N}` |
| `/health` | GET | Provider status | — | `{"status": "ok", "provider": "qwen-local-container", "model": "qwen3.5-4b"}` |

**Provider Layer**:
```
providers/
├── base.py         ← LLMProvider Protocol
├── qwen_local.py   ← Local Qwen3.5-4B provider (base, full precision — not fine-tuned)
└── resolver.py     ← get_provider() — selects by tier
```

**Key Design Decisions**:

1. **Protocol-based design** (Python Protocol, not ABC):
   - Structural subtyping — no inheritance required
   - Easy to mock for testing
   - Clear interface: `chat()`, `complete()`

2. **Local Qwen3.5-4B container** (not AWS Bedrock, not OpenAI):
   - Single model family: Qwen3.5-4B (dense, natively multimodal — text, image, video; 262K ctx; Apache 2.0; ~8 GB BF16, ~2.5–3 GB Q4)
   - "Cloud" = a local Docker container on the laptop; $0, fully offline-capable
   - Serves **base** Qwen3.5-4B (full precision, **not** fine-tuned) for Premium + RAG
   - On-device (Frame 10): Free = base quantized; Premium = fine-tuned quantized (React Native / Neural Engine / Metal)
   - Embeddings stay Qwen3-VL-Embedding-2B (same family)

3. **Stateless requests**:
   - No session management between requests
   - Each request is independent
   - Provider selected per-request by tier

#### 2. Fine-Tune Service (`services/finetune/`)

**Responsibility**: Manage **local** LoRA fine-tuning jobs over Qwen3.5-4B.

| Endpoint | Method | Description | Request | Response |
|----------|--------|-------------|---------|----------|
| `/train` | POST | Submit training job | `{"user_id": "...", "dataset_path": "..."}` | `{"job_id": "...", "status": "submitted"}` |
| `/status/:job_id` | GET | Get training status | — | `{"job_id": "...", "status": "...", "metrics": {...}}` |
| `/health` | GET | Service status | — | `{"status": "ok"}` |

**Training Pipeline**:
```
Triples (JSONL) → Format conversion → Local LoRA over Qwen3.5-4B → LoRA adapter → Model version
                                                                    → Premium on-device build merges + quantizes (Q4) for React Native
                                                                    → Cloud container stays base (not fine-tuned)
```

**Key Design Decisions**:

1. **LoRA** (Low-Rank Adaptation), run **locally** (PEFT / ms-swift / Unsloth):
   - Parameter-efficient (<1% of weights trained)
   - Lower compute cost than full fine-tuning — runs on the laptop (or Colab free)
   - Preserves base model capabilities
   - Produces an adapter merged + quantized for the **Premium** on-device React Native build (cloud stays base)

2. **Background worker**:
   - Training jobs run asynchronously
   - Status polled via `/status/:job_id`
   - Training can take hours — not blocking

3. **Dataset from Frame 2**:
   - Input: triples extracted by ETL service (ETL calls the base Qwen3.5-4B in the LLM Service)
   - Format: convert triples to the local LoRA training format
   - Triggered manually via `POST /api/finetune` (not automatic)

### Configuration

**LLM Service** (`services/llm/config.py`):
```python
# Local Qwen3.5-4B container
QWEN_MODEL_ID: str = "qwen3.5-4b"
QWEN_ADAPTER_PATH: str | None = (
    None  # LoRA adapter path (Premium on-device build only; cloud unused)
)

# Service
LLM_HOST: str = "0.0.0.0"
LLM_PORT: int = 8003
```

**Fine-Tune Service** (`services/finetune/config.py`):
```python
# Local LoRA over Qwen3.5-4B
BASE_MODEL_ID: str = "qwen3.5-4b"
LORA_BACKEND: str = "peft"  # peft / ms-swift / unsloth

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
The ETL Service (Frame 2) calls the same service's base Qwen3.5-4B to extract triples.

### Migration from Monolith

| Monolith file | Destination | Notes |
|---------------|-------------|-------|
| `services/api/llm/base.py` | `services/llm/providers/base.py` | Protocol — no changes |
| `services/api/llm/*.py` (provider) | `services/llm/providers/qwen_local.py` | Local Qwen3.5-4B provider |
| `services/api/llm/resolver.py` | `services/llm/providers/resolver.py` | Resolver — update imports |
| `services/api/config.py` (LLM部分) | `services/llm/config.py` | Extract LLM-related config |

After Frame 4 is complete and tested, `services/api/` (monolith) is deleted.

### Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Local container memory footprint (~8 GB BF16) | Use Q4 quantization (~2.5–3 GB) where needed; Matryoshka budget for embeddings |
| LoRA training quality | Monitor loss curves, validate with test set |
| Laptop compute for training | LoRA is parameter-efficient; can also run on Colab free |
| Provider switching | Stateless requests, no session dependency |
