---
title: Skill distribution mechanisms
labels: [wayfinder:research]
status: open
assignee:
blocked-by: []
---

## Question

What are the current mechanisms for packaging and distributing an agent
skill/tool like this glossary, and what does each require and lock us into?
Cover at least: the `npx skills` installer ecosystem (skills.sh / Vercel's
skills registry — how install works, where files land, multi-harness support),
Claude Code plugins (marketplace, `plugin` command), a plain git repo cloned
into `~/.claude/skills`, and npm-package-with-postinstall. For each: install
UX, update story, whether it can carry non-skill assets (scripts, hooks, MCP
config), and harness portability. The answer feeds the packaging decision.

Findings branch: `research/skill-distribution` (worktree).
