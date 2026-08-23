---
name: ai-glossary-setup
description: Install, repair, or uninstall the personal AI glossary — a user-global terminology file imported into every session. Use when the user asks to set up, fix, or remove their glossary.
---

# Personal AI glossary setup

Bootstraps the glossary: one `glossary.md` in a harness-neutral data home,
loaded into every Claude Code session through a single `@`-import line in
`~/.claude/CLAUDE.md`. After setup the running system is just that file plus
that line — this skill is only the install, repair, and uninstall surface.

The **data home** is `$XDG_CONFIG_HOME/ai-glossary/`
(`~/.config/ai-glossary/` when `XDG_CONFIG_HOME` is unset). Resolve it to an
absolute path once at the start and use that path everywhere below.

## Setup — and repair, which is the same idempotent run

1. Create the data home directory if it doesn't exist.
2. If `<data home>/glossary.md` is absent, copy `templates/glossary.md` from
   this skill's folder there. An existing file holds the operator's
   vocabulary — leave it exactly as it is.
3. Ensure `~/.claude/CLAUDE.md` contains the import line
   `@<data home>/glossary.md`. Create the file if it's missing; append the
   line only when no line already imports that glossary path.
4. Announce what changed, path by path. If everything already existed, say
   setup was already complete.

Done when the data home and `glossary.md` exist, the import line appears
exactly once in `~/.claude/CLAUDE.md`, and every write has been announced.

## Uninstall

1. Remove the glossary `@`-import line from `~/.claude/CLAUDE.md`, leaving
   the rest of the file untouched.
2. Leave the data home in place — the glossary is the operator's vocabulary,
   never a side effect to delete. Tell the operator where it still lives so
   removing it stays their call.

Done when no glossary import remains in `~/.claude/CLAUDE.md` and the
operator knows where their data is.
