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

Every AAF issue body carries exactly one fenced `aaf-metadata` block whose field names and spellings are exact:

````markdown
```aaf-metadata
type: delivery
priority: 0
parent: null
depends_on: []
active_specialist: null
implementation_specialists: []
input_revisions: []
required_checks: ["python3 -m pytest skills/ai-glossary-setup/tests/test_manage.py", "ruff check ."]
completion_claims: ["C1"]
created: 2026-08-30
updated: 2026-08-30
```
````

`type` is one of `delivery | research | integration | coordination` for workflow purposes; delivery classifications (`feature`, `bugfix`, `docs`, `hotfix`, `refactor`, `chore`) remain branch/PR classifications. Claims appear one per line under `## Claims`, each with a stable ID that is never changed or removed once recorded:

```markdown
## Claims

- claim: id=C1 | The settings page persists the theme on reload
```

Results are append-only record lines under their sections. Under `## Review`, a verdict line is followed by its finding lines; a finding binds to one claim ID or is scoped `observed-outside`:

```markdown
## Evidence

- completion-evidence: revision=<40-char sha> | <command run and observed result>
- check-result: name=pytest | passed=true | revision=<40-char sha>

## Review

- review: verdict=changes-required | reviewer=<name> | revision=<40-char sha>
- finding: claim=C1 | <defect against a stated requirement, with evidence>
- finding: scope=observed-outside | <defect the issue never promised>
```

A verdict is `accepted`, `changes-required`, or `evidence-required`, never `Verdict: Changes Required` prose or an HTML comment. A verdict written in any other dialect is a counterfeit record: nothing reads it and every gate that depends on it silently never runs. `done` requires, at the revision named by the last `completion-evidence` line, a `passed=true` `check-result` for every `required_checks` entry and a final `accepted` `review` line whose reviewer is not in `implementation_specialists` and which follows the latest evidence or check line.

Tracker records and comments never expose resolved local machine paths — home directories, XDG config directories, or AAF scratch roots. Record each such path in its unresolved environment-variable form, keeping the repository-identity and assignment-id components: a local `<config>/aaf/scratch/<repo-identity>/<assignment-id>/` worktree is recorded as `${XDG_CONFIG_HOME:-~/.config}/aaf/scratch/<repo-identity>/<assignment-id>/`. Agents resolve the real path locally for verification and cleanup; only the recorded copy stays unresolved.

The body also carries outcome/constraints, completion boundary, and exit criterion in prose sections around the structured blocks. Validate dependencies and state against the recorded fields; do not introduce parallel issue files.

### Durable Branch Linking

When the orchestrator creates an implementation issue's durable branch, it links the branch to the issue using GitHub's native branch-linking so the association is visible on the issue. Where native linking is unavailable, add a clickable branch reference (a `refs/heads/...` link or a branch-mention line) to the issue body or a comment instead — never leave the branch as an unlinked local branch.

### Activity Comments

Issue comments record append-only activity:
- Actor, event, prior/current claim, evidence, authority, and next action.
- Revision-linked check executions and reviewer verdicts (`accepted`, `changes-required`, `evidence-required`).
- Operator approvals, failure reports, and state transitions.
- Pre-implementation research reports.

