#!/usr/bin/env python3
"""PROTOTYPE — UserPromptSubmit hook: inject glossary entries matched by the prompt.

Matches the prompt against each entry's term, aliases, AND anti-terms (using an
anti-term is exactly when the canonical entry should appear). Emits only the
matching lines; empty output when nothing matches.
"""
import json
import os
import re
import sys

payload = json.load(sys.stdin)
prompt = (payload.get("prompt") or "").lower()

project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
glossary_path = os.path.join(project_dir, "..", "glossary.md")

ENTRY = re.compile(r"^- \*\*(?P<term>.+?)\*\* — .*?(?:\*\((?P<tail>.*?)\)\*)?$")


def phrases(line_match):
    words = [line_match.group("term")]
    tail = line_match.group("tail") or ""
    for part in tail.split(";"):
        part = part.strip()
        for prefix in ("not:", "aka:"):
            if part.startswith(prefix):
                words += [w.strip() for w in part[len(prefix):].split(",")]
    return [w.lower() for w in words if w.strip()]


matched = []
with open(glossary_path) as f:
    for line in f:
        m = ENTRY.match(line.rstrip())
        if not m:
            continue
        for phrase in phrases(m):
            if re.search(r"\b" + re.escape(phrase) + r"\b", prompt):
                matched.append(line.rstrip())
                break

if matched:
    out = (
        "Personal glossary — terms relevant to this prompt "
        "(use the canonical term; avoid anything under 'not:'):\n"
        + "\n".join(matched)
    )
    print(out[:9500])
