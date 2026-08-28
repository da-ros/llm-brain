# Architecture Diagrams — llm-brain

Draw.io XML diagrams for the AI-Augmented Digital Brain architecture.

## 📁 Diagram Files

| File | C4 Level | Description |
|------|----------|-------------|
| `c4-context.drawio` | Level 1 | System Context — actors, system, external dependencies |
| `c4-container.drawio` | Level 2 | Containers — apps, services, data stores |
| `c4-component-api.drawio` | Level 3 | API Backend components — FastAPI modules |
| `c4-component-mobile.drawio` | Level 3 | Mobile App components — React Native modules |
| `mcp-agent-flow.drawio` | — | MCP Agent flow — Ingestor → Razonador → Evaluador |
| `deployment.drawio` | — | Deployment — Local (Docker) + Production (ECS Fargate) |
| `tech-stack.drawio` | — | Technology stack decisions with rationale |

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

## 📤 Export Options

### Export as PNG/SVG
1. Open the diagram in Draw.io
2. File → Export as → PNG/SVG
3. Set quality and size

### Export as PDF
1. Open the diagram in Draw.io
2. File → Export as → PDF

## 🎨 Customization

All diagrams use standard Draw.io shapes:
- **C4 shapes**: `mxgraph.c4.c4_*` (system, container, component, cloud)
- **Flowchart shapes**: `mxgraph.flowchart.*`
- **Basic shapes**: `mxgraph.basic.*`

Colors follow a consistent scheme:
- 🔵 Blue (`#dae8fc`): Clients, UI components
- 🟡 Yellow (`#fff2cc`): Backend, API, configuration
- 🟢 Green (`#d5e8d4`): LLM, AI/ML, data processing
- 🟣 Purple (`#e1d5e7`): API Gateway, external services
- 🔴 Red (`#f8cecc`): Fine-tuning, security, infrastructure
- ⚪ Gray (`#f5f5f5`): External systems, cloud services

## 📚 References

- [C4 Model](https://c4model.com/) — Architecture documentation
- [Draw.io](https://www.drawio.com/) — Free diagramming tool
- [AWS C4 Stencils](https://github.com/awslabs/aws-icons-for-draw.io) — AWS shapes

## 🔄 Updates

When architecture changes:
1. Edit the `.drawio` file in Draw.io
2. Save and commit
3. Update this README if new diagrams are added
