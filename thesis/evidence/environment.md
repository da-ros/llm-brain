# Environment snapshot

Taken on 17 November 2026 while writing the evidence index. This is the
machine and the checkout at that moment. It is not a claim that job
`ft-job-56f3ab60` ran on this commit. The training log does not record a
git SHA.

| Item | Value |
|------|--------|
| Machine | MacBook Pro (Mac16,8), Apple M4 Pro, 48 GB |
| OS | macOS 26.5.1 (build 25F80) |
| Python | 3.13.3 |
| Docker | 27.3.1 |
| Docker Compose | v2.30.3-desktop.1 |
| Branch | `feat/testing-fixes-8` |
| Commit | `52d7bd65fa47ea9e9bbbfc9706c4a316e2bd27ef` |
| Host LLM | Port 8003, base Qwen3.5-4B, `LLM_BACKEND=qwen_local` on this Mac |
| Fine-tune | Port 8004, host process. Compose does not publish that port |
| Phone runtime | `llama.rn`, GGUF Q4_K_M. Neural Engine is not used |
| Retrieval | `RAG_TOP_K` default 8 |
| Chat timing | `POST /chat` uses `stream: false`. The round records complete-response time only |

A later measured run replaces this table with the commit that was checked
out when that run started.
