# Frame 2 — Memory Distillation Architecture Diagrams

Draw.io XML diagrams for the One-Tap Memory Distillation module.

## 📁 Diagram Files

| File | Description |
|------|-------------|
| `etl-architecture.drawio` | Architecture base — shows how Frame 2 integrates with Frame 1 (ETL Service, local MongoDB GridFS, LLM Service) using LangChain loaders + LLM-based triple extraction |
| `etl-dataflow.drawio` | Data flow — step-by-step flow: file upload → LangChain loader → LLM Service (Qwen3.5-4B base) reasoning → JSONL triples output |

> **Note:** These `.drawio` XML files still depict stale technology (PyPDF2, Tesseract,
> BeautifulSoup parsers and rule-based triple extraction). They must be regenerated to
> reflect LangChain out-of-the-box loaders and LLM-first triple extraction via the LLM
> Service (port 8003, base Qwen3.5-4B). The `.md` artifacts in this change are the current
> source of truth until the diagrams are updated.

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

- 🔵 **Blue** (`#dae8fc`): Existing Frame 1 components, Auth/Response flow
- 🟢 **Green** (`#d5e8d4`): New Frame 2 components, Parsing/Processing
- 🟡 **Yellow** (`#fff2cc`): Validation decisions, Data extraction
- ⚪ **Gray** (`#f5f5f5`): External stores, Future integrations
- 🔴 **Red** (`#f8cecc`): Error paths

## 📚 References

- [C4 Model](https://c4model.com/) — Architecture documentation
- [Frame 1 Diagrams](../../objective-1-0-architecture-repo/output/diagrams/) — Base architecture
