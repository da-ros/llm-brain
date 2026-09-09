# Frame 3 — Hybrid Store + RAG Architecture Diagrams

Draw.io XML diagrams for the Hybrid Store + RAG module.

## 📁 Diagram Files

| File | Description |
|------|-------------|
| `rag-architecture.drawio` | Architecture base — shows how Frame 3 integrates with Frame 1 (FastAPI, local MongoDB/GridFS) and Frame 2 (JSONL triples) |
| `rag-dataflow.drawio` | Data flow — step-by-step ingestion path (JSONL → chunking → embedding → storage) and retrieval path (query → cross-modal search → context injection) |

> ⚠️ **Stale tech to regenerate in the `.drawio` XML** (not editable here): both diagrams still
> show `MongoDB Atlas` (should be local MongoDB + GridFS), `sentence-transformers` / `384 dimensions`
> (should be Qwen3-VL-Embedding-2B / 2048-dim, multimodal), `Pinecone` as an active store
> (should be Chroma-only for the MVP; Pinecone = future), and `AWS Bedrock` (should be the local
> Qwen3.5-4B container). Regenerate the diagrams to match the updated artifacts.

## 🔧 How to Open

### Option 1: Draw.io Desktop (Recommended)
1. Download from https://www.drawio.com/downloads
2. Open the `.drawio` file directly

### Option 2: Draw.io Web
1. Go to https://app.diagrams.net
2. Click "Open Existing Diagram"
3. Select the `.drawio` file

### Option 3: VS Code Extension
1. Install "Draw.io Integration" extension
2. Open the `.drawio` file directly in VS Code

## 🎨 Color Scheme

- 🔵 **Blue** (`#dae8fc`): Existing components, Retrieval path
- 🟢 **Green** (`#d5e8d4`): New RAG components, Ingestion path
- 🟡 **Yellow** (`#fff2cc`): Encryption, Validation decisions
- ⚪ **Gray** (`#f5f5f5`): External stores (MongoDB, Chroma, LLM)

## 📚 References

- [C4 Model](https://c4model.com/) — Architecture documentation
- [Frame 1 Diagrams](../../objective-1-0-architecture-repo/output/diagrams/) — Base architecture
- [Frame 2 Diagrams](../../objective-2-memory-distillation/output/diagrams/) — ETL pipeline
