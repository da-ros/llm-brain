# llm-brain — AI-Augmented Digital Brain

> MSc Software thesis MVP: a single-tenant personal LLM/OS emulating a **Brain–LLM symbiosis**
> for infinite human memory, personal knowledge management (PKM), advanced reasoning and
> decision-making support.

**Authors:** Pedro David Rodas Mantilla · Giovanny Daniel Jácome Cajamarca
**Tutor:** Ing. Rodolfo Bojorque, PhD · **Institution:** UPS
**Research line:** Sistemas Informáticos e Inteligencia Artificial en Ciencia de Datos

## What it does

Integrates PKM with fine-tuned LLMs, RAG, agentic AI coordinated via **MCP**, and explainable
prompt engineering to help a user **remember, reason, and decide** over their personal data.

## Modules (mapped to the thesis objectives)

| # | Module | Path |
|---|--------|------|
| 1 | Architecture & repo (C4, MCP diagram, CI) | `docs/architecture/`, `infra/` |
| 2 | One-Tap Memory Distillation (ETL → JSON triples) | `services/etl/` |
| 3 | Hybrid store + RAG (Mongo + Chroma/Pinecone + LangChain) | `services/rag/` |
| 4 | LLM fine-tune (LoRA) + on-device proxy (GGUF/ollama) | `notebooks/`, `infra/` |
| 5 | Symbiotic Learning Loop (MCP: Ingestor/Razonador/Evaluador) | `services/agents/` |
| 6 | Decision-Support Simulator (what-if) | `services/simulator/` |
| 7 | Life Analytics (React + Chart.js) | `apps/web/` |
| 8 | Privacy & Scam Shield | `services/shield/` |
| 9 | Alpha validation & KPIs | across modules + `apps/api/` |

## Repository layout

```text
llm-brain/
├─ openspec/       # Spec-driven development: specs (truth) + changes (proposals)
├─ apps/
│  ├─ api/         # FastAPI backend
│  └─ web/         # React + Chart.js dashboard
├─ services/
│  ├─ etl/         # One-Tap Memory Distillation
│  ├─ rag/         # LangChain + vector store
│  ├─ agents/      # MCP Ingestor / Razonador / Evaluador
│  ├─ simulator/   # Decision-Support Simulator
│  └─ shield/      # Privacy & Scam Shield
├─ notebooks/      # Colab LoRA fine-tuning + experiment log
├─ infra/          # docker-compose, ollama proxy
└─ docs/           # C4 diagrams, architecture
```

## Spec-driven development (OpenSpec)

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) to align on specs before
code. Each module is an OpenSpec **change** (`proposal → specs → design → tasks`) that is
archived into `openspec/specs/` once implemented — building a traceable record for the defense.

```bash
openspec list            # active changes
openspec show <change>   # view a change
openspec validate        # validate spec formatting
```

In Cursor, drive the workflow with slash commands: `/opsx-propose`, `/opsx-apply`, `/opsx-archive`.

## Getting started

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in secrets
```

## Tech stack

Python 3.13 · FastAPI · LangChain · React + Chart.js · MongoDB Atlas · Chroma/Pinecone ·
ollama + llama-cpp-python · Docker Compose · GitHub Actions. **LLM is model-agnostic**
(open-source models such as Qwen/DeepSeek/GLM, or cloud via OpenRouter — selectable via config).

## Budget

Targets **$0** using OSS + free tiers; max pre-authorized ~$40 (Colab Pro + contingency).
