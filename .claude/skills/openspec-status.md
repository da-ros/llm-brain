---
name: openspec-status
description: "Check OpenSpec project status — frames, tasks, and progress"
trigger: "/opsx-status"
---

# OpenSpec Status

Check the current status of the OpenSpec project.

## When to use
- When the user wants to know project progress
- When checking which objectives are complete
- When the user says "status", "progress", "what's done"

## Steps

1. **Read project config:**
   - `openspec/config.yaml` — 9 objectives mapped to frames

2. **Check each frame:**
   - `openspec/changes/<objective>/` — Does it exist?
   - `proposal.md` — Is it filled or still TODO?
   - `design.md` — Is it filled or still TODO?
   - `tasks.md` — How many tasks completed?

3. **Calculate progress:**
   - Total objectives: 9
   - Frames created: count
   - Frames with content: count
   - Tasks completed vs total

4. **Display status:**
   - Progress bar or percentage
   - Per-objective status
   - Blockers or next steps

## Output
- Overall progress (X/9 objectives)
- Per-objective status table
- Next recommended actions
- Any blockers or issues
