---
name: curate-glossary
description: Review the current conversation interactively for vocabulary worth persisting in the personal glossary.
disable-model-invocation: true
---

# Curate the personal glossary

Review the operator's messages visible before this skill was invoked. Find
portable vocabulary worth persisting, then interview the operator one candidate
at a time. This is a review surface: every change requires approval even though
agents may curate directly during ordinary work.

Before reading a glossary, inspect the current global `CLAUDE.md` and
`AGENTS.md` managed blocks. Prefer the `ai-glossary:curation` JSON comment's
`canonical_glossary` and `sync_command` pair. For an older block without that
comment, pair its path after `For this installation, edit` with the exact fenced
command after `by running`. If either block supplies a pair, use it together; if
both supply one, require the pairs to match. Stop and ask the operator to repair
setup when metadata is malformed or incomplete, or the pairs conflict. Never
combine a canonical path from one source with a synchronization command from
another.

When no current managed block supplies the pair, resolve the canonical glossary
from `$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to
`~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or empty,
and pair it with `manage.py setup` from the installed `ai-glossary-setup` skill
folder using the same environment defaults. If the paired canonical file or
setup script does not exist, stop and tell the operator to invoke
`ai-glossary-setup`.

Read only the canonical glossary from the resolved pair. Keep that exact pair
unchanged for the whole interview.

## Build the candidate set

Before asking the first question, build one stable set of at most ten
candidates. Only the operator's pre-invocation messages are evidence; agent
messages and the interview itself never add candidates.

A candidate must be portable: its meaning survives moving to another repo.
Project-specific language belongs in that repo's `CONTEXT.md`.

Include only strong evidence:

1. an explicit terminology correction;
2. a distinctive term used repeatedly;
3. terms the operator explicitly treats as aliases;
4. an existing glossary term used with a materially changed meaning.

Repeated verbose references to the same concept also qualify: infer and offer a
concise, precise term and one-line meaning, and label the proposal as inferred.
Collapse candidates that name one concept, preferring the more precise canonical
term. When a candidate matches an existing term, prefer refining that term over
adding a duplicate unless the evidence establishes a real distinction.

Rank candidates in the order above and break ties by frequency. Keep only the
first ten. This caps candidate decisions, not clarification or revision turns.
Do not show discarded weak candidates. If none qualify, say
`No useful glossary candidates found.` and stop.

## Review one candidate at a time

For each candidate, show:

- the exact supporting quote or quotes from the operator;
- why the evidence qualifies;
- one proposed glossary line following the file's entry grammar;
- the choices **approve**, **revise**, **reject**, and **stop**.

Ask only about this candidate, then wait. A rejection means "not during this
invocation" and creates no durable record. A stop ends immediately. Revisions
may merge or invalidate candidates already in the stable set, but never add new
ones.

Terms are unlocked unless the operator requests a lock. If an existing term is
locked, state that approval grants consent only for the exact proposed edit.

## Apply each approval immediately

After approval, edit the installed glossary immediately, preserving its header
and unrelated terms exactly. Keep every term on one line and the flat term list
alphabetized. Validate both grammar and ordering after the write. If validation
fails, report the problem and stop rather than continuing with a malformed file.

After validation, immediately run:

```sh
python3 <ai-glossary-setup skill folder>/manage.py setup
```

Run the synchronization command from the same resolved pair used for the edit.
With defaults, it reads the same XDG/default data home and synchronizes the
generated blocks in `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md` and
`${CODEX_HOME:-~/.codex}/AGENTS.md`; the managed-block form includes matching
`--data-home`, `--claude-file`, and `--agents-file` overrides. Report and stop if
synchronization fails; never edit a managed block directly.

Then ask about the next still-valid candidate. Ending normally or through
**stop** produces no summary: approved terms are already persisted and
synchronized.
