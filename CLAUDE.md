# ai-glossary

## Agent skills

### Issue tracker

Issues are tracked as GitHub Issues on `A-NGJ/ai-glossary` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (created lazily). See `docs/agents/domain.md`.

### Workflow policy

Agile Agentic Flow (AAF) workflow policy: `.workflow/policy.md`. Orchestrators must read this policy before scheduling and supply that policy, tracker guidance (`docs/agents/issue-tracker.md`), and domain references (`docs/agents/domain.md`) to each assignment.
