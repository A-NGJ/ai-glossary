# Personal Glossary

Operator meta-language — these terms are how the operator names things; use
them. Inside a repo, its CONTEXT.md wins on conflict.

Use terms naturally — never announce or narrate that you are applying the
glossary. When the operator uses an anti-term, gently point to the canonical
term; don't just avoid the anti-term in your own reply.

Curation: you maintain this file. Add explicit terminology corrections
immediately. Add a distinctive coined term after the operator uses it
repeatedly; refine a meaning when usage drifts. Capture only portable language
whose meaning survives moving to another repo — project terms belong in that
repo's CONTEXT.md. Mention every change in passing. Ask before deleting an
entry. An entry marked `locked` (or a leading 🔒) keeps its wording unless the
operator consents to change it.

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
