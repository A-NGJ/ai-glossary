# PROTOTYPE — Loading-strategy test bench

Throwaway. Answers [Loading-strategy prototype (#3)](https://github.com/A-NGJ/ai-glossary/issues/3):
which loading strategy *feels* right — a small always-loaded glossary, or an
indexed on-demand lookup?

One realistic 51-term `glossary.md` (grammar per
[Term entry shape and data home (#4)](https://github.com/A-NGJ/ai-glossary/issues/4)),
wired into three scratch projects:

| Variant | Mechanism | What the research predicts |
| --- | --- | --- |
| `variant-a-always` | `@../glossary.md` import in CLAUDE.md | Guaranteed presence; linear token cost every session |
| `variant-b-skill` | `.claude/skills/glossary/` lookup skill | ~1 sentence idle cost; model may never invoke it |
| `variant-c-hook` | `UserPromptSubmit` hook (`.claude/hooks/glossary_inject.py`) | Deterministic injection, but only of entries whose term/alias/anti-term appears in *your prompt* |

## Setup

Run the variants **outside** this repo so its CLAUDE.md/CONTEXT.md (which are
glossary-themed) don't contaminate the reading. From the repo root, on branch
`prototype/loading-strategy`:

```sh
git archive prototype/loading-strategy prototype/loading-strategy | tar -x -C "$TMPDIR"
cd "$TMPDIR/prototype/loading-strategy"
```

Then `cd` into a variant and run `claude`. Notes:

- Variant A: the `@../glossary.md` import resolves outside the project dir — approve
  the one-time dialog.
- Variant C: the hook needs trust in the project's `.claude/settings.json` — accept
  the prompt on first run. Injected context is visible in the transcript (ctrl+o).
- Your `~/.claude/CLAUDE.md` still loads everywhere — that's the realistic condition.

## Probes

Run the same four in each variant, fresh session each time. None mentions the
glossary; don't hint at it.

1. **Production** — "Draft a short GitHub issue proposing we split the upcoming auth
   refactor across multiple agent sessions." Does it write *effort / map / ticket /
   frontier / exit criterion*, or *epic / story / done*? (Variant C predicts a miss
   here: the prompt contains no glossary words, so nothing injects.)
2. **Loop vocabulary** — "My coding agent keeps looping without finishing. What
   should I add to stop that?" Look for *hard iteration cap, no-progress detection,
   exit criterion, Ralph loop*.
3. **Comprehension** — "A teammate left this note on my issue: 'add the packaging
   question to the fog and claim the seeding ticket.' Explain in plain words what
   they want me to do." A translation task, not an action — a fresh scratch session
   has no map or tickets to act on, so asking it to *do* it would only measure the
   missing referents. Does it translate correctly without asking? (B: watch whether
   the skill actually fires; C: hook verified to inject *fog/claim/ticket*.)
4. **Anti-term** — "Write one paragraph on how the user approves changes in this
   tool." Does it correct to *operator*? (C verified to inject the *operator* entry
   because "user" is an anti-term.)

Also run `/context` once per variant and note what the glossary costs.

## Scorecard

Fill in after each session; judgment is the operator's.

| | A always | B skill | C hook |
| --- | --- | --- | --- |
| 1 Production — canonical terms unprompted? | | | |
| 2 Loop vocabulary? | | | |
| 3 Comprehension without asking? | | | |
| 4 Anti-term corrected? | | | |
| Mechanism observed firing (B invoked / C injected)? | n/a | | |
| Token cost (`/context`) | | | |
| Gut feel | | | |
