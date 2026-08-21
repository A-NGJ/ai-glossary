---
title: Prior art — existing personal-glossary tools
labels: [wayfinder:research]
status: closed
assignee: research-subagent
blocked-by: []
---

## Question

Does something like this already exist — a personal, cross-project vocabulary
or ubiquitous-language store shared with AI agents? Survey: agent-skill
registries (skills.sh, Claude Code plugin marketplaces), agent memory
products (Claude Code memory, ChatGPT memory, mem0 and similar), PKM-to-agent
bridges (Obsidian MCP servers), and DDD tooling for glossaries. For each hit:
what it stores, how agents consume it, whether it's personal (cross-project)
or per-repo, and whether it does propose-then-approve capture. The answer
tells us whether to adopt, imitate, or ignore — and may reshape the build
tickets.

Findings branch: `research/prior-art` (worktree).

## Resolution

Full findings: `research/prior-art.md` on branch `research/prior-art`
(commit f10fc34). Verdict: **imitate** — nothing combines all four
requirements (personal scope, structured vocabulary, agent consumption,
propose-then-approve), but each exists in isolation:

- Best capture loop: `citypaul/.dotfiles@ubiquitous-language` on skills.sh —
  DETECT → PROPOSE ("never adopt; STOP and present to the human") → DECIDE →
  RECORD → RENAME — but per-repo. Steal the protocol.
- Best scope: `terrylica/cc-skills@glossary-management` — user-global
  `~/.claude/docs/GLOSSARY.md` as cross-project SSoT with hooks — but no
  approval gate. Steal the location idea.
- Matt Pocock's `ubiquitous-language` skill was retired in favour of
  per-repo `domain-modeling`/CONTEXT.md; memory products (mem0, Letta, Zep,
  ChatGPT memory) store unstructured facts with probabilistic retrieval and
  no approval queue; Contextive is mature ubiquitous-language tooling but
  per-repo, IDE-facing, no agent integration.
- Claude Code's user-global `~/.claude/CLAUDE.md` is the ideal auto-loaded
  substrate; its auto-memory capture channel is per-project only.
- Design tension for the term-shape ticket: DDD says vocabulary is
  per-bounded-context, so the personal glossary should own the operator's
  *meta*-language ("effort", not "epic") and defer to per-repo glossaries
  for domain terms via an explicit precedence rule.
