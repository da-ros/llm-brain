---
name: openspec-propose
description: "Propose a new OpenSpec change frame with proposal, design, specs, and tasks"
trigger: "/opsx-propose"
---

# OpenSpec Propose

Create a new change frame in `openspec/changes/` with all planning artifacts.

## When to use
- When the user wants to propose a new feature or change
- When starting work on a new objective (1-9)
- When the user says "propose", "new change", or "create frame"

## Steps

1. **Identify the objective** — Ask which objective (1-9) or create a new frame name
2. **Read context** — Read `openspec/config.yaml` and `openspec/input/context.txt`
3. **Create frame directory** — `openspec/changes/<frame-name>/`
4. **Create artifacts:**
   - `.openspec.yaml` — metadata
   - `proposal.md` — Why + What (reference anteproyecto)
   - `design.md` — How (architecture decisions, rationale)
   - `tasks.md` — Task breakdown with dependencies
   - `specs/<capability>/spec.md` — Formal requirements with scenarios

## Rules
- Architecture-first: document WHAT before HOW
- Reference anteproyecto for justification
- Include Non-goals section in proposal
- Include Decisions Made section in design
- Tasks must have acceptance criteria
- Tasks must show dependencies

## Output
- Frame created with all artifacts
- Summary of what was created
- Prompt: "Artifacts ready for review. Run `/opsx-apply` when ready to implement."
