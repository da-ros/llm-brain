# Frame 2 — Memory Distillation Architecture Diagrams

Draw.io XML diagrams for the One-Tap Memory Distillation module.

## 📁 Diagram Files

| File | Description |
|------|-------------|
| `etl-architecture.drawio` | Architecture base — shows how Frame 2 integrates with Frame 1 (FastAPI backend, MongoDB, Chroma) |
| `etl-dataflow.drawio` | Data flow — step-by-step flow from file upload to JSONL triples output |

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
- [Frame 1 Diagrams](../../objective-1-architecture-repo/diagrams/) — Base architecture
