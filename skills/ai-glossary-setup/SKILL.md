---
name: ai-glossary-setup
description: Install, repair, or uninstall the personal AI glossary — canonical vocabulary synchronized into global Claude and AGENTS instructions. Use when the user asks to set up, fix, sync, or remove their glossary.
---

# Personal AI glossary setup

Run this skill's `manage.py`; it performs the file transformation rather than
asking the harness to interpret an import. The canonical vocabulary remains in
`<data home>/glossary.md`. Setup and repair copy its complete current content
between managed markers in both global instruction files:

- Claude Code: `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`
- AGENTS.md-based Codex harnesses: `${CODEX_HOME:-~/.codex}/AGENTS.md`

The **data home** is `$XDG_CONFIG_HOME/ai-glossary/`, falling back to
`~/.config/ai-glossary/`. The script expands these defaults itself. Use its
path from this skill's folder, regardless of the current working directory.

## Setup and repair

Run:

```sh
python3 <skill folder>/manage.py setup
```

The command creates missing parent directories and files. It seeds a missing
canonical glossary from `templates/glossary.md`, but never replaces an existing
canonical glossary. For each global instruction file, it removes legacy
`@.../ai-glossary/glossary.md` lines and all prior managed blocks, preserves
other content, then writes exactly one current block delimited by:

```text
<!-- ai-glossary:managed:start -->
...
<!-- ai-glossary:managed:end -->
```

A rerun therefore synchronizes edits made to the canonical glossary and does
not duplicate blocks. Report each path printed by the command; `setup already
complete` means no bytes needed changing.

Done when the command exits zero, the canonical glossary exists, and both
global files contain exactly one managed block with its complete content.

## Uninstall

Run:

```sh
python3 <skill folder>/manage.py uninstall
```

The command removes every managed block and legacy glossary import line from
both global instruction files while preserving all other content. It leaves the
data home and canonical glossary in place and prints that retained path.

Done when the command exits zero and its retained glossary path has been
reported to the operator.

## Isolated or nonstandard targets

For tests, sandboxes, or explicit nonstandard installations, override every
path without touching live global files:

```sh
python3 <skill folder>/manage.py setup \
  --data-home /absolute/data-home \
  --claude-file /absolute/CLAUDE.md \
  --agents-file /absolute/AGENTS.md
```

Use the same options with `uninstall`. Relative override paths are accepted but
absolute paths make the changed targets unambiguous.
