---
name: openspec-apply
description: "Apply an OpenSpec change — implement the tasks from a frame"
trigger: "/opsx-apply"
---

# OpenSpec Apply

Implement the tasks defined in an OpenSpec change frame.

## When to use
- When the user wants to implement a change
- After `/opsx-propose` when artifacts are ready
- When the user says "apply", "implement", or "execute"

## Steps

1. **Identify the frame** — Which objective or frame to implement
2. **Read frame artifacts:**
   - `proposal.md` — Understand what and why
   - `design.md` — Understand architecture decisions
   - `tasks.md` — Get task list with dependencies
   - `specs/` — Get acceptance criteria
3. **Execute tasks in order:**
   - Follow dependency order from tasks.md
   - Create/update code files
   - Create/update documentation
   - Run tests after each task
4. **Update tasks.md** — Mark completed tasks with `[x]`
5. **Validate** — Run tests, check CI, verify acceptance criteria

## Rules
- Follow architecture-first approach (design before code)
- Respect decisions made in design.md
- Create files only when needed (don't pre-create)
- Run tests after each significant change
- Update OpenSpec artifacts if implementation diverges

## Output
- Code implemented per tasks.md
- Tests passing
- Documentation updated
- Summary of what was implemented
- Any deviations from design documented
