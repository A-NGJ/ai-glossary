# ai-glossary

A personal, cross-project glossary for AI coding agents: your terms and
one-line meanings, kept in one canonical user-global `glossary.md` and
synchronized into global Claude Code and AGENTS.md instructions. The glossary
curates itself in the open — automatically at the end of every Claude Code and
Opencode session, adding explicit corrections and distinctive repeated terms,
announcing each change, asking before any deletion, and never rewording
locked entries.

## Install

```sh
npx skills add A-NGJ/ai-glossary
```

To reinstall both skills into every supported agent directly from this checkout
while developing, run `make install-local`. This includes uncommitted local
changes.

Then ask your agent to run the `ai-glossary-setup` skill. It creates the data
home (`$XDG_CONFIG_HOME/ai-glossary/`, defaulting to `~/.config/ai-glossary/`),
writes `glossary.md` from a template if you don't have one, and embeds its
complete content in clearly delimited managed blocks in:

- `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md` for Claude Code
- `${CODEX_HOME:-~/.codex}/AGENTS.md` for AGENTS.md-based Codex harnesses

The files and their parent directories are created when absent. Existing
instructions outside the managed blocks are preserved.

Setup also idempotently installs automatic curation: a Claude Code
`SessionEnd` hook and an Opencode plugin, both invoking the same offline,
rule-based command at the end of every session. It reads only the operator's
own messages from that session, and writes any qualifying unlocked term —
explicit corrections and aliases unconditionally, plus distinctive terms
repeated often enough with a supporting sentence — straight to the canonical
glossary, reporting each addition in passing. It never deletes a term or
rewords a locked one, and it makes no network or LLM calls.

Run the user-invoked `curate-glossary` skill when you want an interactive
review of vocabulary from the current conversation instead of, or in addition
to, that automatic pass. It finds at most ten strong, portable candidates,
asks you to approve or reject them one at a time, writes each approval
immediately to the canonical file, and synchronizes both managed copies after
every write.

Fallback without the `skills` CLI:

```sh
git clone https://github.com/A-NGJ/ai-glossary.git
ln -s "$(pwd)/ai-glossary/skills/ai-glossary-setup" ~/.claude/skills/ai-glossary-setup
```

## Repair and uninstall

Re-running the setup skill is idempotent: it recreates missing files and
replaces each managed block with the canonical glossary's current complete
content. This propagates glossary edits without duplicating blocks. Setup also
removes legacy glossary `@`-import lines.

Asking it to uninstall removes only managed blocks, legacy glossary import
lines, and the managed automatic-curation hook and plugin from both global
instruction files. It preserves unrelated instructions, hooks, and plugins,
and leaves the data home in place: deleting your vocabulary is your call,
never a side effect.

## How it works

- **Data home**: `$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to
  `~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or empty —
  harness-neutral; put its directory under git yourself if you want history.
- **Loading**: setup synchronizes the whole glossary into managed blocks in the
  global Claude Code and Codex AGENTS.md files. Harnesses read ordinary inline
  instructions; no nonstandard `@` expansion is required.
- **Format**: one line per term —
  `- **term** — one-line meaning. *(locked; not: anti-terms; aka: aliases)*`.
  The curation rules live in the file's own header, so they travel with the
  data to any harness that can read a markdown file.
- **Precedence**: inside a repo, that repo's CONTEXT.md wins on conflict —
  the personal glossary holds portable meta-language, not project domain terms.
- **Curation**: agents edit only the canonical glossary, then immediately rerun
  setup to regenerate both managed copies; managed blocks are never edited
  directly. `curate-glossary` applies this automatically after each approved
  write; automatic curation applies it after every qualifying candidate found
  at session end.
