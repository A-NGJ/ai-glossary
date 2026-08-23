# VALIDATION — Proof of use

Throwaway. Answers [Proof of use (#11)](https://github.com/A-NGJ/ai-glossary/issues/11):
does the *installed* tool make a Claude Code session demonstrably use the
operator's terminology unprompted?

Unlike the [prototype bench (#3)](https://github.com/A-NGJ/ai-glossary/issues/3),
nothing here wires anything up: the real, seeded
`~/.config/ai-glossary/glossary.md` (27 terms) rides its `@`-import in
`~/.claude/CLAUDE.md`. The probes are rebuilt against the terms that survived
the seeding review, and a fifth check validates **shadowing** — a repo
CONTEXT.md winning over the personal glossary on conflict — using the
`shadow-repo/` in this directory.

**Bar** (per the ticket): passing probes 1 and 4. The shadowing probes are a
scope addition from the resolving session, recorded on the ticket.

## Setup

- Probes 1–4 run in an **ordinary repo of yours** — any real project whose
  CLAUDE.md/CONTEXT.md is not glossary- or wayfinder-themed (that would
  contaminate the reading). Just `cd` there and run `claude`.
- Probes 5a–5b run in `shadow-repo/`. Copy it outside this repo first:

  ```sh
  git archive validation/proof-of-use validation/proof-of-use/shadow-repo | tar -x -C "$TMPDIR"
  cd "$TMPDIR/validation/proof-of-use/shadow-repo"
  claude
  ```

- Fresh session per probe. None of the prompts mentions the glossary — don't
  hint at it.

## Probes

Target terms in brackets are what to watch for; the prompt itself never
contains them.

1. **Production** — "Draft a short GitHub issue proposing that we plan the
   upcoming auth refactor across several agent sessions before anyone builds
   it." [wayfinding, decision ticket, fog of war, exit criterion, HITL/AFK,
   worktree — vs. generic *epic / story / phases / done*]
2. **Loop vocabulary** — "My coding agent keeps looping without finishing.
   What should I add to stop that?" [hard iteration cap, exit criterion,
   goal drift, context rot]
3. **Comprehension** — "A teammate left this note on my issue: 'this one's
   AFK — run it in a worktree in yolo mode, and watch for goal drift.'
   Explain in plain words what they want me to do." A translation task: does
   the session unpack all four terms correctly without asking?
4. **Anti-term** — "Write one paragraph on how the user approves changes made
   by an agent in this kind of tool." [corrects *user* → **operator**]
5. **Shadowing** — in `shadow-repo/`, whose CONTEXT.md deliberately conflicts
   with the personal glossary:
   - **5a Anti-term reversal** — "Where should I record this bug so it
     doesn't get lost?" The repo canonizes **backlog** and rejects *issue
     tracker* — the exact reverse of the personal glossary. Does the session
     say *backlog*?
   - **5b Meaning conflict** — "Explain what seeding means in this project."
     The repo defines **seed** as an RNG initializer; the personal glossary
     as hand-picked bootstrap content. Does the repo meaning win?

Also run `/context` once in the ordinary repo and note what the glossary
costs.

## Scorecard

Fill in after each session; judgment is the operator's.

| Probe | Pass? | Notes |
| --- | --- | --- |
| 1 Production — canonical terms unprompted? | | |
| 2 Loop vocabulary? | | |
| 3 Comprehension without asking? | | |
| 4 Anti-term corrected to *operator*? | | |
| 5a Shadowing — *backlog* wins in shadow-repo? | | |
| 5b Shadowing — repo meaning of *seed* wins? | | |
| Token cost of glossary (`/context`) | | |
| Gut feel | | |
