# Frame 1.1 — API Router Architecture Diagrams

Draw.io XML diagrams for the API Router (Gateway) service.

## 📁 Diagram Files

| File | Description |
|------|-------------|
| `api-router-architecture.drawio` | Architecture base — shows API Router with JWT, correlation ID, Kafka, MongoDB |
| `api-router-dataflow.drawio` | Data flow — upload async (Kafka) and query sync (HTTP) flows |

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

- 🔵 **Blue** (`#dae8fc`): Clients
- 🟡 **Yellow** (`#fff2cc`): API Router
- 🟢 **Green** (`#d5e8d4`): Services (ETL, RAG, LLM)
- 🟣 **Purple** (`#e1d5e7`): AWS API Gateway
- 🔴 **Red** (`#f8cecc`): Kafka (async)
- ⚪ **Gray** (`#f5f5f5`): Data stores (MongoDB)

## 📚 References

- [C4 Model](https://c4model.com/) — Architecture documentation
- [Frame 1 Diagrams](../../objective-1-architecture-repo/diagrams/) — Base architecture
