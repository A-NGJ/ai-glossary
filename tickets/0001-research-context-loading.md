---
title: How Claude Code loads context
labels: [wayfinder:research]
status: open
assignee:
blocked-by: []
---

## Question

What are the actual mechanics and token costs of the ways a glossary could
reach a Claude Code session's context? Cover: always-loaded files (CLAUDE.md
and its global/project variants — size limits, load order), skills (frontmatter
descriptions always visible vs bodies loaded on invoke), MCP tools (when tool
descriptions are loaded, cost per tool), hooks (can a hook inject context per
prompt?), and the memory system. For each: when does the content enter
context, what does an idle (unused) integration cost per session, and can it
scale with glossary size? The answer feeds the loading-strategy decision
(always-loaded-and-small vs indexed-on-demand).

Findings branch: `research/claude-context-loading` (worktree).
