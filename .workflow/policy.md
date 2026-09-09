# Workflow Policy

<!-- AAF-MANAGED: policy-schema 1.0.0 — do not remove this marker -->

<!--
  This file defines the repository's workflow policy for Agile Agentic Flow.

  Sections marked OPERATOR-CONFIGURABLE may be edited freely.
  Sections marked CONTRACT-INVARIANT reflect shared contract guarantees;
  their semantics cannot be weakened, but the surrounding text may be
  adapted to local conventions.
  Sections marked AAF-MANAGED are maintained by AAF tooling; manual edits
  will be overwritten on upgrade.
-->

## Tracker

<!-- OPERATOR-CONFIGURABLE -->

- Source of truth: the issue-tracker adapter selected in `.workflow/aaf.yml` (`github-issues`).
- Authoritative tracker guidance: `docs/agents/issue-tracker.md`.
- Conversations, harness state, PR descriptions, and second trackers are not authoritative records.
- Only the orchestrator writes issue records, updates metadata, or changes issue workflow state.
- Specialists and reviewers receive tracker records as read-only inputs.
- Every assignment, including in an isolated worktree, receives readable policy and its linked authority as accessible absolute source paths or exact read-only snapshots carrying source paths and content hashes. Dispatch blocks if authority is inaccessible; the orchestrator revalidates authority before accepting results.

## Roles

<!-- CONTRACT-INVARIANT: authority and role invariants -->

- **Orchestrator**: Exactly one coordinates each active intent graph. It alone mutates workflow state, delegates assignments, owns the durable issue branch and draft PR, posts research, and mechanically applies unchanged conflict-free commits. It never edits product artifacts or resolves conflicts.
- **Implementation Specialist**: Owns one bounded repository-changing assignment at a time. It cannot broaden intent, weaken completion, write tracker state, own the durable issue branch, or communicate/delegate directly to specialists. All communication goes through the orchestrator and artifacts.
- **Researcher**: Read-only. Sourced findings, access dates, uncertainty, and implications go to the orchestrator. Receives no worktree, modifies no artifacts/state, and makes no product-direction decisions. Pre-implementation research is a separate blocking issue. Reports are posted as append-only research comments. Stateful experiments or generated repository artifacts are prototype/implementation assignments, not read-only research.
- **Reviewer**: Fresh independent read-only reviewer assesses every correctness-bearing integrated attempt or research report, returning `Accepted`, `Changes Required`, or `Evidence Required`. Reviewers cannot modify artifacts or workflow state. Each finding is reported as either against a stated requirement of the issue under review or as a defect observed outside those requirements. Reviewers receive no earlier round's findings and hold no authority over loop termination.
- **Operator**: Explicitly approves every implementation PR; only an operator merges it. Agents never approve or merge on the operator's behalf.
- No agent performs cross-harness session resume, automatic package updates, or automatic repository-policy migrations as an incidental part of any assignment; each needs its own bounded, operator-approved scope.

## States

<!-- CONTRACT-INVARIANT: three required phases -->

Required phases: `todo`, `in-progress`, `done`.

<!-- OPERATOR-CONFIGURABLE: optional states and tracker mapping -->

Optional states enabled: `backlog`, `blocked`, `cancelled`.
Workflow state maps to GitHub Issues labels:
- `todo` -> `todo`
- `in-progress` -> `in-progress`
- `done` -> `done`
- `backlog` -> `backlog`
- `blocked` -> `blocked`
- `cancelled` -> `cancelled`

<!-- CONTRACT-INVARIANT: Done semantics -->

An issue reaches Done only when:
1. every dependency is Done;
2. its completion evidence is recorded;
3. the integrated product state meets the completion boundary;
4. a fresh reviewer returns Accepted;
5. for PR delivery, the explicitly operator-approved revision is merged into the configured integration branch (`main`);
6. all temporary worktrees are cleaned up.

## Completion Boundary

<!-- OPERATOR-CONFIGURABLE: checks and evidence -->

The local-project completion boundary is:
- observable revision-linked verification evidence is recorded (e.g. Markdown validation, skill structure and path verification; no automated test/lint script is currently configured);
- changed observable behavior has executable evidence where applicable;
- current required consumer documentation is updated;
- a fresh independent review returns Accepted;
- for implementation delivery, explicit operator approval, PR merge into `main`, and temporary-worktree cleanup are verified.

<!-- CONTRACT-INVARIANT: boundary invariants -->

- An issue may strengthen this boundary. Weakening it requires operator approval recorded in Activity and cannot waive AAF minimums.
- Material product or evidence changes after review invalidate acceptance and operator approval. Operator remarks, failed checks, conflicts, or revision changes keep or return work to In Progress for correction, fresh independent review, and fresh approval before completion.
- Pure coordination parents use their declared outcome evidence without redundant review.
- Non-code issues meet their configured artifact, evidence, review, and approval boundary.
- Research may finish without branch, worktree, or PR when its report, citations, uncertainties, independent review, and required operator approval satisfy its boundary.

## Scheduling

<!-- AAF-MANAGED:BEGIN scheduling-invariants -->

- One orchestrator coordinates an active intent graph.
- One implementation specialist owns an issue at a time.
- Dependencies are explicit and separate from parent-child links.
- Only Todo issues with all dependencies Done and merged where applicable, with stable inputs and available capacity, are runnable. Interdependent work is sequential; no stacked PRs or early dependent starts.

<!-- AAF-MANAGED:END scheduling-invariants -->

<!-- OPERATOR-CONFIGURABLE: concurrency and priority -->

- Maximum concurrent implementation specialists: 3.
- Priority is operator-controlled: a larger integer runs first; `0` is the default. Ties are broken by the lower issue ID.
- Backlog enters Todo only after operator approval is recorded in Activity.

## Delivery and Isolation

<!-- AAF-MANAGED:BEGIN isolation-invariants -->

- Integration branch: `main`.
- Delivery classifications: `feature`, `bugfix`, `docs`, `hotfix`, `refactor`, `chore`.
- Durable branch naming: `<type>/<issue>-<slug>`.
- Each implementation issue has one durable branch and one draft PR; pre-Done corrections stay there. Defects after Done become new issues and delivery lines. Merged issue branches are deleted by default.
- Every repository-changing assignment uses a fresh temporary worktree and temporary assignment branch created from the current durable issue-branch revision under `${XDG_CONFIG_HOME:-~/.config}/aaf/scratch/<repo-identity>/<assignment-id>/`.
- Implementation specialists return a bounded commit. The orchestrator applies it unchanged only if conflict-free, serializing integration. Semantic conflicts require another specialist assignment.
- Specialists cannot write `.workflow/` or tracker state.
- Specialists do not communicate or delegate directly to other specialists.
- Reviewers inspect the exact integrated revision read-only without worktrees.
- Ready for operator review requires passing checks/evidence, fresh Accepted review, and removal of all temporary worktrees. Cleanup failure keeps work In Progress.

<!-- AAF-MANAGED:END isolation-invariants -->

## Retry, Escalation, and Failure

<!-- OPERATOR-CONFIGURABLE: retry and escalation counts -->

- Identical retries are allowed only for safe, evidence-backed transient failures.
- Maximum identical attempts: 2.
- Maximum Changes Required verdicts for the same unresolved claim: 2.
- The second Changes Required verdict triggers operator escalation before another implementation attempt.
- Hitting the retry limit requires changed parameters or approach, or operator escalation.
- Maximum review rounds per issue (unconditional, lifetime): 3. A review round is any recorded verdict that is not `Accepted` — counted whether or not its findings repeat an earlier round's, so the bound cannot be avoided by raising a different finding each round. Before dispatching any assignment for an issue already under review, the orchestrator counts that issue's recorded non-accepted verdicts and does not dispatch at the maximum. At the maximum it clears the active specialist, records the escalation with every outstanding finding and its routing, keeps the issue In Progress, and stops. The count resets only on recorded operator re-authorization.
- Route reviewer findings by what the issue promised: a finding against a stated requirement of the issue under review stays in that issue for its next implementation assignment; a defect observed outside those requirements becomes a successor issue, with the issue under review depending on that successor only when the defect blocks its acceptance. Never hold an issue open for defects it never promised to resolve.

<!-- CONTRACT-INVARIANT: failure handling invariants -->

- Failure reports record failed step, cause/evidence, completed work, useful partial commit hashes, discarded work, retry safety, and recommended recovery.
- The orchestrator records durable facts in the tracker before cleanup.
- Useful work is preserved as marked partial commits when safe, or explicitly reported as none. Partial commits are replacement inputs, not directly integrated commits.
- The failed worktree is removed before replacement starts; its temporary branch is retained only while referenced partial commits are needed, and deleted after recovery succeeds or partial work is rejected.
- Replacement assignments receive the report and commits in a fresh worktree, never the failed workspace.

## Review

<!-- AAF-MANAGED:BEGIN review-invariants -->

Each integrated attempt is reviewed by a fresh specialist. The reviewer receives only authoritative artifacts and returns one of:
- `Accepted`
- `Changes Required`
- `Evidence Required`

The reviewer has read-only tracker access and cannot edit artifacts or workflow state. Only the orchestrator moves an issue to Done.

<!-- AAF-MANAGED:END review-invariants -->

## Quality

<!-- OPERATOR-CONFIGURABLE -->

Code and documentation must expose behavior through modular interfaces, explicit contracts, executable tests (where applicable), and consumer documentation. Inline comments explain only facts that cannot be derived from code.

CRAP checks are disabled until the project selects an analyzer and defines its measurement unit and coverage source.

<!-- AAF-MANAGED: end policy-schema 1.0.0 -->
