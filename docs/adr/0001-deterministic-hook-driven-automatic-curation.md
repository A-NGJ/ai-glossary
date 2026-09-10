# Deterministic, hook-driven automatic curation

_Superseded by [ADR-0002](0002-description-triggered-model-invoked-curation.md)
— description-triggered, model-invoked curation. The reasoning below is
retained for history._

The glossary previously only grew when the operator remembered to invoke the
manual `curate-glossary` skill, so useful vocabulary could be lost at the end
of an unremembered session. We decided to trigger curation automatically at
session end — via a Claude Code `SessionEnd` hook and an Opencode
`session.idle` plugin — but to run it through the same shared, rule-based
Python command already used for setup/uninstall, rather than adding
harness-specific logic or an LLM-backed extractor. Both harness adapters are
thin: they gather that session's own messages and shell out to one command,
which owns parsing, candidate selection, contextual meaning inference,
validation, an advisory lock around the canonical read-modify-write, and
managed-block synchronization.

We chose a deterministic, offline engine (regex-based rules plus stopword/
frequency filtering, zero network calls) over an LLM-backed one specifically
to keep automatic curation zero-cost and reviewable; the engine still exposes
a clear seam (`find_candidates`) where an optional LLM extractor could later
compete alongside the rule-based candidates without changing the harness
adapters or the write path. We chose full autonomous writes for qualifying
unlocked terms — not an approval queue — because the operator explicitly
accepted that trade-off in exchange for an in-passing notice per change;
locked terms and deletions remain excluded from autonomous action, and the
manual `curate-glossary` skill remains available for an explicit,
approval-based pass.
