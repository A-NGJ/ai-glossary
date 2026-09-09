# Personal AI Glossary

A user-global vocabulary store: the operator's meta-language, read by AI
agents so they speak the operator's words, curated by agents in the open
with the operator holding veto and per-term locks.

## Language

**Operator**:
The human whose vocabulary the glossary records. There is exactly one per
glossary — the tool is personal, not team-scoped.
_Avoid_: user, owner

**Term**:
A canonical word or phrase the operator uses, together with its one-line
meaning. The unit the glossary stores.
_Avoid_: entry, definition, word

**Meaning**:
The single line of prose that says what a term is. One line is a hard limit,
enforced by the file grammar.
_Avoid_: description, definition

**Anti-term**:
A word the operator rejects in favor of a canonical term ("I say *effort*,
not *epic*" — *epic* is the anti-term). Rendered in an entry's `not:` list.
_Avoid_: rejected term, banned word

**Alias**:
A word the operator accepts as equivalent to a canonical term. Rendered in
an entry's `aka:` list.
_Avoid_: synonym

**Glossary file**:
The single markdown file holding all terms as a flat, alphabetized bullet
list — one line per term, self-describing header, directly inlinable into
agent context.
_Avoid_: database, store

**Data home**:
The user-global directory the glossary file lives in:
`$XDG_CONFIG_HOME/ai-glossary/` (falling back to `~/.config/ai-glossary/`),
a plain directory — versioning it is the operator's choice. Harness-neutral —
no AI tool owns it; each harness reaches into it.
_Avoid_: config dir, storage location

**Meta-language**:
The layer of vocabulary the glossary owns: portable operator language whose
meaning survives moving to another repo. Project-specific terms belong to that
repo's own glossary.

**Shadowing**:
The precedence rule between glossary layers: inside a repo, its `CONTEXT.md`
wins on conflict; the personal glossary is the cross-project fallback.
_Avoid_: override, never-overlap

**Curation**:
Maintenance of the glossary file, by either of two surfaces: automatic
curation, which runs unattended at session end, or the curation skill, which
runs interactively on operator request. Both add only unlocked terms and
never delete or reword a locked term without explicit consent.
_Avoid_: auto-capture

**Automatic curation**:
The unattended curation pass a session-end hook or plugin triggers after
every Claude Code and Opencode session. It runs its own deterministic,
offline, rule-based candidate engine — separate from the interactive
curation skill's LLM-judgment path — covering explicit corrections,
aliases, and definitions unconditionally, plus distinctive terms the
operator repeated often enough with a supporting contextual sentence. It
writes every qualifying unlocked term directly to the canonical glossary
without asking first, then reports each addition in passing. It considers
only the operator's own messages from that session, never assistant
wording. It never deletes a term or reworks a locked one.
_Avoid_: auto-capture, background curation, per-turn curation

**Curation hook**:
The harness-side lifecycle adapter that triggers automatic curation: a
Claude Code `SessionEnd` hook, or an Opencode plugin listening for the
session-idle lifecycle event. Each adapter only gathers that session's
messages and invokes the shared curation command; all parsing, candidate
selection, and canonical writes live in the shared command, not the adapter.
Setup installs both idempotently; uninstall removes only these two managed
integrations, leaving unrelated hooks and plugins untouched.
_Avoid_: webhook, trigger script


**Lock**:
A per-term flag (`locked` in the entry's italic group, or a leading 🔒)
forbidding an agent from rewording or removing that term without the
operator's explicit consent.
_Avoid_: pin, freeze

**Managed glossary block**:
A marker-delimited generated copy of the canonical glossary embedded in a
harness's global instruction file. Agents edit only the canonical file and
immediately run setup to replace both blocks; uninstall removes them without
touching unrelated instructions.
_Avoid_: import, editable glossary

**Setup skill**:
The agent-performed installer and maintenance surface. Idempotently bootstraps
the data home and glossary file, synchronizes managed glossary blocks into
global Claude Code and AGENTS.md instructions, and installs the curation hook
integrations (a Claude Code `SessionEnd` hook and an Opencode plugin) that
trigger automatic curation; uninstall removes those blocks, legacy import
lines, and the managed hook integrations, but leaves the data home and any
unrelated hooks or plugins untouched.
_Avoid_: install script, installer plugin

**Curation skill**:
The user-invoked interactive review that inspects only the operator's messages
in the current conversation and ranks up to ten strong, portable candidates:
explicit corrections, repeated coined terms, aliases, then meaning drifts, with
frequency breaking ties. Repeated verbose references to one concept qualify for
a concise inferred term and meaning. The skill collapses overlapping candidates
toward the more precise term and prefers refining a matching existing term. It
presents evidence and a proposed line one candidate at a time for approval,
revision, rejection, or stopping. Each approval is written immediately to the
canonical file, validated for grammar and alphabetical order, and synchronized
to both managed blocks before continuing; terms remain unlocked unless the
operator requests a lock. Rejection means not during this invocation. Ending
produces no summary; when nothing qualifies, it reports that no useful candidate
was found. It remains available for an explicit, approval-based pass over the
current conversation even though automatic curation runs unattended at every
session's end.

**Harness**:
An AI tool that consumes the glossary (Claude Code is the first). The
glossary is harness-neutral; harnesses adapt to it, never the reverse.
