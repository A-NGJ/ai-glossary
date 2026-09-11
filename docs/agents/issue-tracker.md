# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.

## Agile Agentic Flow (AAF) Mechanics

This repository uses the `github-issues` AAF tracker adapter targeting `A-NGJ/ai-glossary` via `gh`.

### Roles and Authority

- Exactly one issue tracker (`github-issues` on GitHub) is authoritative.
- Only the orchestrator creates and updates tracker records or changes workflow state. Specialists receive read-only tracker records.
- GitHub assigns issue numbers; no local issue directory or locally allocated IDs exist.

### Workflow State Mapping

Workflow state is tracked via dedicated labels (open/closed status alone is not the workflow phase):

| Phase | GitHub Label | Meaning |
| ----- | ------------ | ------- |
| `todo` | `todo` | Authorized and eligible to run |
| `in-progress` | `in-progress` | Active under assignment |
| `done` | `done` | Merged and completed |
| `backlog` | `backlog` | Optional: awaiting operator approval |
| `blocked` | `blocked` | Optional: waiting on dependency or decision |
| `cancelled` | `cancelled` | Optional: abandoned with history preserved |

### Issue Record Structure

Every AAF issue body contains structured metadata, outcome/constraints, completion boundary, and evidence sections:

```markdown
<!-- aaf-metadata
type: feature | bugfix | docs | hotfix | refactor | chore
priority: 0
parent: null | <issue-number>
depends_on: []
active_specialist: null
input_revisions: []
required_checks: ["python3 -m pytest skills/ai-glossary-setup/tests/test_manage.py", "ruff check ."]
created_at: YYYY-MM-DDTHH:MM:SSZ
updated_at: YYYY-MM-DDTHH:MM:SSZ
-->

## Outcome
Why this issue exists and observable result.

## Constraints and Uncertainty
Known limitations, non-goals, and identified uncertainties.

## Completion Boundary and Exit Criterion
Explicit exit criterion and required checks/evidence.

## Evidence and Verification
Revision-linked verification commands, results, and independent review verdicts.
```

### Activity Comments

Issue comments record append-only activity:
- Actor, event, prior/current claim, evidence, authority, and next action.
- Revision-linked check executions and reviewer verdicts (`Accepted`, `Changes Required`, `Evidence Required`).
- Operator approvals, failure reports, and state transitions.
- Pre-implementation research reports.

