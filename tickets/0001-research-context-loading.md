---
title: How Claude Code loads context
labels: [wayfinder:research]
status: closed
assignee: research-subagent
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

## Resolution

Full findings: `research/claude-context-loading.md` on branch
`research/claude-context-loading` (commit a2a706e), verified against
code.claude.com docs (memory, hooks).

- **CLAUDE.md**: all variants load in full at session start (delivered as a
  user message, not system prompt); no hard size limit but docs target
  <200 lines per file for adherence. `@path` imports auto-load arbitrary
  files — `@~/.claude/glossary.md` in the user CLAUDE.md works today.
- **Skills**: idle cost is name+description only (~a sentence each); body
  loads on invoke and stays. No guarantee the model invokes it.
- **MCP**: tool search on by default — only tool names idle; weakest
  usage guarantee.
- **Hooks**: `SessionStart` / `UserPromptSubmit` stdout (exit 0) becomes
  visible context, capped at 10,000 chars — enables deterministic,
  relevance-matched glossary injection that scales with glossary size.
- **Auto memory**: per-project and Claude-pruned — wrong home for a
  user-curated glossary. `--append-system-prompt` isn't persistent.
- **Recommended shape**: two tiers — small core always-on via `@`-import;
  long tail via a UserPromptSubmit hook (guaranteed, relevance-based) or a
  skill (cheaper, best-effort). Feeds the prototype and the
  loading-strategy decision.
