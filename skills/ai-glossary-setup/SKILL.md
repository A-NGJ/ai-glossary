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
`~/.config/ai-glossary/` when `XDG_CONFIG_HOME` is unset or empty. The script
expands these defaults itself. Use its
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

Each generated block also identifies the canonical file, forbids direct block
edits, and embeds the exact command and resolved canonical/target paths needed
to synchronize that installation. A rerun therefore synchronizes canonical
edits and does not duplicate blocks. Report each path printed by the command;
`setup already complete` means no bytes needed changing.

Done when the command exits zero, the canonical glossary exists, and both
global files contain exactly one managed block with its complete content.

Setup also idempotently installs the two automatic-curation integrations
described below: a Claude Code `SessionEnd` hook in
`${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json`, and an Opencode plugin file
at `$XDG_CONFIG_HOME/opencode/plugin/ai-glossary-curate.js` (falling back to
`~/.config/opencode/plugin/`). Both point back at this same `manage.py` with
the resolved data-home and target paths, and are marked internally so setup
can update them and uninstall can remove them without touching any other
hook or plugin.

## Automatic curation

At the end of every Claude Code session, the managed `SessionEnd` hook — and
at the end of every Opencode session, the managed plugin's `session.idle`
handler — invoke:

```sh
python3 <skill folder>/manage.py curate --source claude   # Claude Code hook
python3 <skill folder>/manage.py curate --source opencode  # Opencode plugin
```

The `curate` action is the single engine shared by both integrations
(`curation.py`): it extracts only operator-authored messages from that
session, evaluates them against deterministic rules — explicit corrections,
aliases, and definitions unconditionally, plus distinctive terms the operator
repeated at least `--min-repetitions` times (default 3) with a supporting
contextual sentence — and, for every resulting candidate that does not
already exist in the canonical glossary (locked or not), appends it as a new
unlocked entry. It holds an advisory lock in the data home around the entire
read-candidate-write-sync sequence, so concurrent sessions serialize instead
of racing. It never deletes a term and never reworks a locked one. It prints
each addition, or reports that no qualifying candidate was found.

Invoke it directly for manual testing:

```sh
python3 <skill folder>/manage.py curate --source claude --transcript /path/to/transcript.jsonl
echo '{"messages": [...]}' | python3 <skill folder>/manage.py curate --source opencode
```

This automatic pass never replaces the user-invoked `curate-glossary` skill,
which remains available for an explicit, approval-based review of the
current conversation.

## Uninstall

Run:

```sh
python3 <skill folder>/manage.py uninstall
```

The command removes every managed block and legacy glossary import line from
both global instruction files while preserving all other content. It also
removes only the managed Claude Code `SessionEnd` hook entry and the managed
Opencode plugin file, preserving every other hook, plugin, and setting. It
leaves the data home and canonical glossary in place and prints that retained
path.

Done when the command exits zero and its retained glossary path has been
reported to the operator.

## Isolated or nonstandard targets

For tests, sandboxes, or explicit nonstandard installations, override every
path without touching live global files:

```sh
python3 <skill folder>/manage.py setup \
  --data-home /absolute/data-home \
  --claude-file /absolute/CLAUDE.md \
  --agents-file /absolute/AGENTS.md \
  --claude-settings-file /absolute/settings.json \
  --opencode-plugin-dir /absolute/plugin
```

Use the same options with `uninstall`. Relative override paths are accepted but
absolute paths make the changed targets unambiguous.
