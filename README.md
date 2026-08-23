# ai-glossary

A personal, cross-project glossary for AI coding agents: your terms and
one-line meanings, kept in one user-global `glossary.md` that every Claude
Code session loads. The agent curates it in the open — adding and refining
terms as your vocabulary settles, announcing each change, asking before any
deletion, and never rewording locked entries.

## Install

```sh
npx skills add A-NGJ/ai-glossary
```

Then ask your agent to run the `ai-glossary-setup` skill. It creates the data
home (`$XDG_CONFIG_HOME/ai-glossary/`, defaulting to `~/.config/ai-glossary/`),
writes `glossary.md` from a template if you don't have one, and adds one
`@`-import line to `~/.claude/CLAUDE.md`.

Fallback without the `skills` CLI:

```sh
git clone https://github.com/A-NGJ/ai-glossary.git
ln -s "$(pwd)/ai-glossary/skills/ai-glossary-setup" ~/.claude/skills/ai-glossary-setup
```

## Repair and uninstall

Re-running the setup skill is idempotent — it recreates whatever is missing
and never touches an existing glossary's entries. Asking it to uninstall
removes the import line but leaves the data home: deleting your vocabulary is
your call, never a side effect.

## How it works

- **Data home**: `$XDG_CONFIG_HOME/ai-glossary/glossary.md` — a plain
  directory, harness-neutral; put it under git yourself if you want history.
- **Loading**: the whole glossary rides one `@`-import in `~/.claude/CLAUDE.md`,
  so it's in context every session — no skill invocation to miss.
- **Format**: one line per term —
  `- **term** — one-line meaning. *(locked; not: anti-terms; aka: aliases)*`.
  The curation rules live in the file's own header, so they travel with the
  data to any harness that can read a markdown file.
- **Precedence**: inside a repo, that repo's CONTEXT.md wins on conflict —
  the personal glossary holds your meta-language, not project domain terms.
