---
name: curate-glossary
description: Review the current conversation for portable vocabulary worth persisting in the personal glossary. Use when the operator coins, corrects, or repeatedly uses distinctive vocabulary worth keeping, or asks to curate the glossary.
---

# Curate the personal glossary

Review the operator's messages visible before this skill was invoked. Find
portable vocabulary worth persisting, then interview the operator one candidate
at a time. Also invoke it whenever the operator wants an explicit,
approval-based pass over the current conversation.

Resolve the canonical glossary from `$XDG_CONFIG_HOME/ai-glossary/glossary.md`,
falling back to `~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is
unset or empty, and pair it with `manage.py setup` from the installed
`ai-glossary-setup` skill folder using the same environment defaults. If the
paired canonical file or setup script does not exist, stop and tell the operator
to invoke `ai-glossary-setup`.

Read only the canonical glossary from the resolved pair. Keep that exact pair
unchanged for the whole interview. Validate the existing term grammar and
alphabetical order before building candidates. If validation fails, report the
problem and stop before asking for approvals or changing any file.

## Entry format

Every term is one line, and the term list stays flat and alphabetized. An
optional italic group at the end carries the term's anti-terms and aliases, in
that order. The format is easiest to learn from worked examples:

- **ubiquitous language** — one shared vocabulary used identically in conversation, docs, and code.
- **session compaction** — summarizing older conversation history so a session fits its context window. *(not: compaction)*
- **hook** — code fired deterministically when an event occurs, not invoked by choice.
- **issue** — a work item recorded in a ticketing system such as GitHub Issues or Jira. *(not: ticket; aka: work item)*

A good term is broad enough to apply beyond one tool or project, yet still
definable in one line; it is a word the operator genuinely uses. Never narrow a
common word to one niche sense — qualify it instead (**session compaction**,
not *compaction*).

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
- one proposed glossary line following the entry format above;
- the choices **approve**, **revise**, **reject**, and **stop**.

Ask only about this candidate, then wait. A rejection means "not during this
invocation" and creates no durable record. A stop ends immediately. Revisions
may merge or invalidate candidates already in the stable set, but never add new
ones.

## Apply each approval immediately

After approval, construct the complete updated glossary in memory, preserving
its header and unrelated terms exactly. Keep every term on one line and the flat
term list alphabetized. Validate the complete proposed content for grammar and
ordering before writing it. If validation fails, report the problem and leave
the canonical file unchanged. Once valid, write the canonical file and
immediately run:

```sh
python3 <ai-glossary-setup skill folder>/manage.py setup
```

Run the synchronization command from the resolved pair used for the edit. With
defaults, it reads the same XDG/default data home and synchronizes the generated
blocks in `${CLAUDE_CONFIG_DIR:-~/.claude}/CLAUDE.md` and
`${CODEX_HOME:-~/.codex}/AGENTS.md`. Report and stop if synchronization fails;
never edit a managed block directly.

Then ask about the next still-valid candidate. Mention every change in passing
as it is written, and ask before deleting an existing entry. Ending normally or
through **stop** produces no summary: approved terms are already persisted and
synchronized.
