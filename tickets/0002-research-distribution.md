---
title: Skill distribution mechanisms
labels: [wayfinder:research]
status: closed
assignee: research-subagent
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

## Resolution

Full findings: `research/skill-distribution.md` on branch
`research/skill-distribution` (commit fda871b), primary-source cited.

- **skills.sh / `npx skills add`**: installs from any public GitHub repo into
  77+ harnesses' skill dirs (symlink by default); `npx skills update` diffs a
  user-global lockfile; no registry; carries scripts/assets but *nothing
  executes at install time* — no hooks/MCP/init.
- **Claude Code plugin**: richest payload (skills, agents, hooks, MCP, bin);
  SessionStart hook + `${CLAUDE_PLUGIN_DATA}` give a clean data-directory
  initializer; Claude Code-only.
- **git clone/symlink into `~/.claude/skills`**: doc-blessed; Cursor and
  OpenCode natively read that dir; hooks possible via `hooks` frontmatter or a
  dropped-in `.claude-plugin/plugin.json`.
- **npm package**: postinstall effectively dead (pnpm blocks it); only viable
  as explicit `npx … init` — no unique capability; skip.
- **Coexistence**: one repo can serve the first three simultaneously.
  Recommended: clean SKILL.md repo first, optional `.claude-plugin/` layer for
  Claude-specific hooks/init, harness-neutral data dir (e.g. `~/.glossary`)
  shared by all channels.
- Open unknown: whether `npx <pkg>@latest` re-resolves per run isn't
  confirmed by official npm docs.
