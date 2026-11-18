# Current runtime

This file is the running system as of 17 November 2026. `openspec/input/context.txt`
is the scope authority. Frame proposals and designs keep the decision each
frame made at the time; when one of those files disagrees with this page, cite
this page for how the system runs and cite the frame for what changed.

The evidence round for Objetivo Específico 9 is
`openspec/changes/objective-9-alpha-validation/` and `thesis/evidence/`.

## Inference

| Path | Where it runs | Weights |
|------|----------------|---------|
| Web free chat | Host process, port 8003 | Base Qwen3.5-4B. No RAG and no memory. |
| Web premium chat | Same host process, reached through `reason_graph` | Same base weights. RAG context is added by the agents service. |
| ETL triple extraction | Same host process, `POST /extract` | Same base weights. |
| Phone, Free | `llama.rn` on the iPhone GPU (Metal) | Base GGUF Q4_K_M, downloaded through the API Router. |
| Phone, Premium, On device | Same `llama.rn` runtime | That user's LoRA pack quantized to Q4, or the base pack when no pack exists. |
| Phone, Premium, Digital Brain | Host process, port 8003, through `POST /api/chat` | Base weights plus that user's RAG memory. |

Docker Compose does not contain an LLM service. Containers call the host at
`http://host.docker.internal:8003`. `LLM_BACKEND` selects the host runtime:
`qwen_local` (PyTorch on Metal on the Mac) or `ollama` (local Ollama on
Linux and Windows). `QWEN_MOCK=true` is the default and overrides either
backend, which is how CI runs. `QWEN_ADAPTER_PATH` defaults to empty, so the
host process stays the base model. The LoRA adapter is not loaded into port 8003.

`llama.rn` loads a GGUF file. ExecuTorch, Core ML, and the Apple Neural Engine
do not run this model. Jest uses `FakeEngine`, which returns 40 ms and 12
tokens so the status screen can render. That pair of numbers is not a handset
measurement.

`POST /chat` and the Ollama provider send `stream: false`. The alpha round
measures complete-response time of the host model only. It does not record
a phone elapsed time.

## Fine-tune

The API Router and the agents service call `http://host.docker.internal:8004`.
Compose defines `finetune-service` and does not publish port 8004. A host
process serves that port. When a batch path arrives as `/app/data/...`, the
host process reads the same files under the repository `data/` directory
(`services/finetune/pipeline.py`, `_host_dataset_path`).

Training is manual. The definitive adapter for the alpha round is
`qwen3.5-4b-lora-v5` for account `57eec20b-9ee6-4e75-bc87-1668a8e5f8b6`
(Nora Vega). The log, the pack manifest, and the rule that excludes the
September `user1` pytest logs are in `thesis/evidence/finetune/`.

## Retrieval and encryption

RAG Top-k is `RAG_TOP_K`, default 8, in `services/rag/config.py` and in
Compose. Precision@3 is an evaluation cut of the first three ranked items.
It is not a second retrieval setting.

Fernet, in `services/rag/vector_store.py`, encrypts chunk text in Chroma's
document field and stores a ciphertext copy of each vector in metadata
`encrypted_vector`. The HNSW index keeps the raw float vectors, because it
cannot search ciphertext.

## Identity and clients

Passwords are PBKDF2-HMAC-SHA256, 200000 iterations, stored as `salt$hash`
(`services/api-router/accounts.py`). The JWT is HS256 and carries
`subscription_tier`. The user document stores `plan`.

The web app is TanStack Start / React. The Life Analytics scatter is drawn
by `apps/web/src/components/encefalus/analytics-page.tsx`. It does not use
Chart.js. Recharts is present on the shared chart primitive and is not that
scatter.

## What CI measures

`.github/workflows/ci.yml` runs on branches other than `main`: ruff, pytest,
and Snyk. The pytest step sets `EMBEDDING_MOCK=true` and the workflow treats
the database and the LLM as mocked. `.github/workflows/docker.yml` runs on
`main` and builds nine images (api-router, etl, rag, finetune, agents,
simulator, shield, analytics, web). The LLM has no image.

A green pytest run supports the functional checks. It does not support
Precision@3, grounding, training loss, or phone latency.

## Leftover wording in code

A few comments still say "LLM container" or "cloud LLM container". They are
comments, not the runtime. The ones to ignore when writing the thesis are
`services/finetune/config.py`, `services/finetune/lora.py`,
`services/simulator/llm_client.py`, and the export note in
`services/finetune/export_on_device.py`. The call path is the host process.
