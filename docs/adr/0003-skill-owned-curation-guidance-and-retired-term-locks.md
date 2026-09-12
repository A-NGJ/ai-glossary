# Skill-owned curation guidance and retired term locks

The tool-owned header of the canonical glossary — the region setup mirrors from
`templates/glossary.md` and embeds in every managed block — used to carry both
how to read and use terms and how to curate them. The curation half stated the
portability rule, the entry grammar, what makes a good term, and worked
examples, and it defined a per-term lock: an entry marked `locked` in its
italic group, or with a leading lock marker, that an agent could not reword or
remove without the operator's explicit consent. Because setup copies the header
into the embedded blocks, those rules traveled with the data to any harness
that could read a markdown file, and the lock gave the operator a durable veto
alongside the approval interview.

We reversed both choices. The header now carries only how to read and use
terms; every curation rule lives in the `curate-glossary` skill, presented
there as concrete worked examples. The embedded header is generated data, and
behavior that governs curation belongs with the skill that performs it, where
it can be expressed as examples and revised alongside the skill rather than
rewritten in every installation's data. The per-term lock was a second source
of state the skill had to interpret, and it did not fit a model that already
asks the operator to approve every change: the approval interview is the only
protection a term needs, so locks are retired completely. No entry carries lock
state, and the skill never rewords or deletes an entry without consent.

Setup rewrites a stale header region to the current template, so every existing
canonical glossary and managed block is migrated on its next run; operator
entries below the `---` separator are preserved byte-for-byte. This retires the
lock-protection clause of
[ADR-0002](0002-description-triggered-model-invoked-curation.md) without
changing its description-triggered, model-invoked curation design.
