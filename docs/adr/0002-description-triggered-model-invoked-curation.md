# Description-triggered, model-invoked curation

The glossary previously grew through a config-mandated automatic pass: a
Claude Code `SessionEnd` hook and an Opencode `session.idle` plugin invoked a
shared, deterministic command at the end of every session, writing qualifying
terms without asking first. That design put the trigger in harness
configuration rather than in the skill, so curation existed only where the hook
or plugin had been installed, and the rule engine that selected candidates was
a second code path — `curation.py` behind a `manage.py curate` action —
maintained alongside the interactive skill.

We replaced it with a single surface: the `curate-glossary` skill carries a
`description` that states both what it does and when to use it, and the model
invokes the skill from that description when the conversation surfaces
portable vocabulary worth keeping. There is no session-end hook, no Opencode
plugin, and no unattended automatic pass; curation happens in the open, in the
conversation, as an approval-based interview that writes one candidate at a
time. We chose a model-invoked, description-driven trigger over harness
configuration because the judgment that a conversation contains
glossary-worthy vocabulary is the judgment the model is already making inside
that conversation, and a deterministic offline rule set only approximated it.
The change also removes the harness-side installation and lifecycle surface
entirely, leaving one curation path instead of two, and lets the skill's own
description travel with it to any harness that can load skills.

This decision supersedes
`0001-deterministic-hook-driven-automatic-curation`. The deterministic engine
it described was deleted and the config-mandated session-end invocation
removed, so the trigger now lives in the skill rather than in agent
configuration. The operator retains the same protections under the new model:
additions remain approval-based and one at a time, locked terms stay locked,
and no term is deleted or reworded without explicit consent.
