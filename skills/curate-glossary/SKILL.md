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

Resolve the **data home** once from `$XDG_CONFIG_HOME/ai-glossary/`, falling
back to `~/.config/ai-glossary/`. Read `<data home>/glossary.md`. If it does not
exist, stop and tell the operator to invoke `ai-glossary-setup`.

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

Then ask about the next still-valid candidate. Ending normally or through
**stop** produces no summary: approved terms are already persisted.
