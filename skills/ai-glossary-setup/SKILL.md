---
name: ai-glossary-setup
description: Install, repair, or uninstall the personal AI glossary — canonical vocabulary synchronized into global Claude and AGENTS instructions. Use when the user asks to set up, fix, sync, or remove their glossary.
---

# Personal AI glossary setup

Run this skill's `manage.py`; it performs the file transformation rather than
asking the harness to interpret an import. The canonical vocabulary remains in
`<data home>/glossary.md`. Setup and repair copy its complete current content
between managed markers in each installed global instruction file:

- Claude Code: `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md`
- AGENTS.md-based Codex harnesses: `${CODEX_HOME:-~/.codex}/AGENTS.md`

By default (no `--claude-file` or `--agents-file`), a target that does not
already exist on disk names a harness that is not installed, so it is left
alone and never created; only targets that already exist are synchronized.
Passing a path explicitly always writes it, creating any missing parent
directories and the file itself. This keeps a Codex-only or Claude-only
installation from gaining an unused config file. A generated managed block
names and synchronizes only the target(s) it lives in.

The **data home** is `$XDG_CONFIG_HOME/ai-glossary/`, falling back to
`~/.config/ai-glossary/` when `XDG_CONFIG_HOME` is unset or empty. The script
expands these defaults itself. Use its
path from this skill's folder, regardless of the current working directory.

## Setup and repair

Run:

```sh
python3 <skill folder>/manage.py setup
```

The command creates missing parent directories and files for active targets. It
seeds a missing canonical glossary from `templates/glossary.md`. If
`<data home>/glossary.md` is a symlink — for example into a dotfiles repo —
setup writes through it to the linked file and leaves the symlink in place, so
the real glossary is updated where the symlink points rather than being
detached.

In the canonical glossary, the **header region** — everything from the start of
the file through the first line whose content is exactly `---` — is tool-owned
and mirrors `templates/glossary.md`. Setup brings a stale header up to the
current template: when that region differs, it replaces only the header region
and prints `migrated <path> header to current template`. Everything after the
`---` separator — every term entry and lock — is preserved byte-for-byte, and
migration runs before the managed blocks are generated so both carry the
migrated header in the same run. When the header already matches, setup makes
no change. A canonical file with no `---` separator is never rewritten, so a
hand-written glossary cannot be clobbered.

For each active global instruction
file, it removes legacy `@.../ai-glossary/glossary.md` lines and all prior
managed blocks, preserves other content, then writes exactly one current block
delimited by:

```text
<!-- ai-glossary:managed:start -->
...
<!-- ai-glossary:managed:end -->
```

Each generated block also identifies the canonical file, forbids direct block
edits, and embeds the exact command and resolved canonical/target paths needed
to synchronize that installation. A rerun therefore synchronizes canonical
edits and does not duplicate blocks. Report each path printed by the command;
`setup already complete` means no bytes needed changing.

Done when the command exits zero, the canonical glossary exists, and each
active global file contains exactly one managed block with its complete
content.

## Uninstall

Run:

```sh
python3 <skill folder>/manage.py uninstall
```

The command removes every managed block and legacy glossary import line from
both global instruction files while preserving all other content. It leaves
the data home and canonical glossary in place and prints that retained path.

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
absolute paths make the changed targets unambiguous. An explicitly passed
target is always written, even when it does not yet exist, so this is the way to
install the glossary into a harness that is not yet on disk.
