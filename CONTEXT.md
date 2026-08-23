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
The layer of vocabulary the glossary owns: the operator's process words,
tool names, and workflow vocabulary — as opposed to any one project's domain
terms, which belong to that repo's own glossary.

**Shadowing**:
The precedence rule between glossary layers: inside a repo, its `CONTEXT.md`
wins on conflict; the personal glossary is the cross-project fallback.
_Avoid_: override, never-overlap

**Curation**:
An agent's direct maintenance of the glossary file — adding terms it observes
the operator using, refining meanings when usage drifts — always announced in
passing in-session, never silent. Deletion always requires asking first.
_Avoid_: proposal, approval queue, auto-capture

**Lock**:
A per-term flag (`locked` in the entry's italic group, or a leading 🔒)
forbidding an agent from rewording or removing that term without the
operator's explicit consent.
_Avoid_: pin, freeze

**Harness**:
An AI tool that consumes the glossary (Claude Code is the first). The
glossary is harness-neutral; harnesses adapt to it, never the reverse.
