---
name: openspec-explore
description: "Explore OpenSpec structure — list frames, check status, view artifacts"
trigger: "/opsx-explore"
---

# OpenSpec Explore

Explore the OpenSpec project structure and frame status.

## When to use
- When the user wants to see project structure
- When the user asks "what frames exist", "show status", "explore openspec"
- When checking what needs to be done

## Steps

1. **List all frames:**
   ```bash
   ls openspec/changes/
   ```

2. **Check frame status:**
   - Which frames have artifacts (proposal, design, tasks)
   - Which frames are empty (TODO templates)
   - Which tasks are completed vs pending

3. **Show project context:**
   - Read `openspec/config.yaml` for project overview
   - Read `openspec/input/context.txt` for current state

4. **Display summary:**
   - Frame list with status
   - Current phase/objective
   - Next steps

## Output
- Project structure overview
- Frame status table
- Current context summary
- Recommended next actions
