# ai-glossary

A personal, cross-project glossary for AI coding agents: your terms and
one-line meanings, kept in one canonical user-global `glossary.md` and
synchronized into global Claude Code and AGENTS.md instructions. The glossary
is curated in the open by the `curate-glossary` skill, which an agent invokes
from the skill's own description whenever the conversation surfaces portable
vocabulary worth keeping — a coined term, an explicit correction, an alias —
and every addition is approved one candidate at a time, asking before any
deletion and never rewording locked entries.

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

Vocabulary is curated by the `curate-glossary` skill. Agents invoke it from
the skill's own description when the conversation surfaces vocabulary worth
keeping — a coined term, an explicit correction, an alias — or whenever you
ask for it. Curation happens in the open, in the conversation; there is no
background or unattended pass.

The skill finds at most ten strong, portable candidates, asks you to approve
or reject them one at a time, writes each approval immediately to the
canonical file, and synchronizes both managed copies after every write. It
never deletes a term or rewords a locked one without your explicit consent.

Fallback without the `skills` CLI:

```sh
git clone https://github.com/A-NGJ/ai-glossary.git
ln -s "$(pwd)/ai-glossary/skills/ai-glossary-setup" ~/.claude/skills/ai-glossary-setup
```

## Repair and uninstall

Re-running the setup skill is idempotent: it recreates missing files and
replaces each managed block with the canonical glossary's current complete
content. The embedded glossary keeps the canonical file's dominant line-ending
style — lone CR for a classic-Mac CR-only file — so regenerating a block never
appends a foreign LF or CRLF before the end marker; the markers themselves stay
LF-delimited. This propagates glossary edits without duplicating blocks. Setup
also removes legacy glossary `@`-import lines.

Setup also reconciles the canonical file's tool-owned header with the bundled
template, so header wording changes reach existing installs without
reinstalling. The header region is everything from the top of the file through
the `---` entries separator; setup replaces it only when it differs, leaves
every term entry and lock below the separator byte-for-byte, and leaves a
glossary with no `---` separator untouched. The replacement header reuses the
canonical file's dominant line-ending style — CRLF, or lone CR for a
classic-Mac CR-only file — so migration does not mix endings. If `glossary.md`
is a symlink —
for example into a dotfiles repo — setup writes through it to the linked file
and leaves the symlink in place, so the real glossary is updated where the
symlink points instead of being detached. A self-referential or looping symlink
names no real target, and so does any other symlink that cannot be resolved to
one (for example, a link pointing through a regular file). Setup refuses each
with an error that names the cause and a non-zero exit instead of replacing the
link with a regular file.

Asking it to uninstall removes only managed blocks and legacy glossary import
lines from the global instruction files. It preserves unrelated instructions
and leaves the data home in place: deleting your vocabulary is your call,
never a side effect.

Both setup and uninstall also clean up the retired deterministic-curation
install shipped by older versions, so upgrading removes it. They remove the
managed Claude Code `SessionEnd` hook entry from
`${CLAUDE_CONFIG_DIR:-~/.claude}/settings.json` and the managed Opencode
`ai-glossary-curate.js` plugin from
`${XDG_CONFIG_HOME:-~/.config}/opencode/plugin/`, each identified by its own
marker. Only those managed artifacts are removed — every other hook, plugin,
group, and settings key is preserved — and a missing file or directory is a
clean no-op.

## How it works

- **Data home**: `$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to
  `~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or empty —
  harness-neutral; put its directory under git yourself if you want history.
- **Loading**: setup synchronizes the whole glossary into managed blocks in the
  global Claude Code and Codex AGENTS.md files. Harnesses read ordinary inline
  instructions; no nonstandard `@` expansion is required.
- **Format**: one line per term —
  `- **term** — one-line meaning. *(locked; not: anti-terms; aka: aliases)*`.
  Everything above the `---` separator is a tool-owned header that setup keeps
  in sync with the bundled template; the curation rules live there, so they
  travel with the data to any harness that can read a markdown file.
- **Precedence**: inside a repo, that repo's CONTEXT.md wins on conflict —
  the personal glossary holds portable meta-language, not project domain terms.
- **Curation**: agents edit only the canonical glossary, then immediately rerun
  setup to regenerate both managed copies; managed blocks are never edited
  directly. The `curate-glossary` skill drives this: each approved candidate is
  written to the canonical file and synchronized before the next question.
