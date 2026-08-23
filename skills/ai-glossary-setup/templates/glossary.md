# Personal Glossary

Operator meta-language — these terms are how the operator names things; use
them. Inside a repo, its CONTEXT.md wins on conflict.

Curation: you maintain this file. When the operator repeatedly uses a term
for something you call differently, add it; refine a meaning when usage
drifts. Mention every change in passing. Ask before deleting an entry. An
entry marked `locked` (or a leading 🔒) keeps its wording unless the operator
consents to change it.

Entry grammar — one line per term, flat and alphabetized:
`- **term** — one-line meaning. *(locked; not: anti-term, …; aka: alias, …)*`
(italic group optional; parts in that order)

What makes a good term: broad enough to apply beyond one tool or project,
yet still definable in one line; a word the operator genuinely uses; never a
common word narrowed to one niche sense — qualify it instead (**session
compaction**, not *compaction*; **fog of war**, not *fog*; **agent
trajectory**, not *trajectory*). Mechanics of this file — locks, the
one-line limit — belong in this header, never as entries.

Examples of good entries:

- **ubiquitous language** — one shared vocabulary used identically in conversation, docs, and code. *(locked)*
- **session compaction** — summarizing older conversation history so a session fits its context window. *(not: compaction)*
- **hook** — code fired deterministically when an event occurs, not invoked by choice (agent-harness hooks, git hooks, webhooks).

---
