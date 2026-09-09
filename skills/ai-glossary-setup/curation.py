#!/usr/bin/env python3
"""Deterministic, offline automatic-curation engine for the personal glossary.

This module is the single curation engine shared by the Claude Code
session-end hook and the Opencode lifecycle plugin. It never makes a network
call and never invokes an LLM: every candidate is produced by fixed parsing
and pattern rules over the operator's own messages.

Public entry points used by ``manage.py``:

- ``extract_operator_messages_claude(transcript_text)``
- ``extract_operator_messages_opencode(payload)``
- ``find_candidates(messages, min_repetitions=DEFAULT_MIN_REPETITIONS)``
- ``parse_glossary(text)`` / ``validate_glossary(text)``
- ``apply_candidates(text, candidates)`` -> ``(updated_text, applied)``
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Glossary entry grammar
# ---------------------------------------------------------------------------

# `- **term** — one-line meaning. *(locked; not: anti-term, …; aka: alias, …)*`
ENTRY_RE = re.compile(
    r"^- \*\*(?P<term>[^*]+)\*\* — (?P<meaning>[^*]+?)\s*"
    r"(?: \*\((?P<flags>[^)]*)\)\*)?$"
)
SEPARATOR_LINE = "---"

# Per the template header, a lock may be rendered either as the `locked` flag
# in the italic group, or as this glyph leading the term itself
# (`- **🔒 anchor** — ...`). Both are lock metadata, never term text: the
# canonical term is always the text with any leading glyph stripped.
LOCK_GLYPH = "🔒"
_LEADING_LOCK_RE = re.compile(rf"^{LOCK_GLYPH}\s*")


@dataclass
class GlossaryEntry:
    term: str
    meaning: str
    locked: bool = False
    not_terms: tuple[str, ...] = ()
    aka_terms: tuple[str, ...] = ()
    # True when this entry's lock is rendered as a leading 🔒 before the term
    # rather than the `locked` flag in the italic group. Tracked separately
    # from `locked` so re-rendering an untouched entry reproduces the exact
    # original lock syntax byte-for-byte.
    locked_prefix: bool = False

    def render(self) -> str:
        term_text = f"{LOCK_GLYPH} {self.term}" if self.locked_prefix else self.term
        flags = []
        if self.locked and not self.locked_prefix:
            flags.append("locked")
        if self.not_terms:
            flags.append("not: " + ", ".join(self.not_terms))
        if self.aka_terms:
            flags.append("aka: " + ", ".join(self.aka_terms))
        suffix = f" *({'; '.join(flags)})*" if flags else ""
        return f"- **{term_text}** — {self.meaning}{suffix}"


def _parse_flags(flags: Optional[str]) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    locked = False
    not_terms: tuple[str, ...] = ()
    aka_terms: tuple[str, ...] = ()
    if not flags:
        return locked, not_terms, aka_terms
    for part in flags.split(";"):
        part = part.strip()
        if not part:
            continue
        if part == "locked":
            locked = True
        elif part.startswith("not:"):
            not_terms = tuple(t.strip() for t in part[len("not:") :].split(",") if t.strip())
        elif part.startswith("aka:"):
            aka_terms = tuple(t.strip() for t in part[len("aka:") :].split(",") if t.strip())
    return locked, not_terms, aka_terms


def parse_entry_line(line: str) -> Optional[GlossaryEntry]:
    match = ENTRY_RE.match(line.rstrip("\n"))
    if not match:
        return None
    locked, not_terms, aka_terms = _parse_flags(match.group("flags"))
    raw_term = match.group("term")
    locked_prefix = bool(_LEADING_LOCK_RE.match(raw_term))
    term = _LEADING_LOCK_RE.sub("", raw_term) if locked_prefix else raw_term
    return GlossaryEntry(
        term=term,
        meaning=match.group("meaning"),
        locked=locked or locked_prefix,
        not_terms=not_terms,
        aka_terms=aka_terms,
        locked_prefix=locked_prefix,
    )


@dataclass
class ParsedGlossary:
    """A canonical glossary split into its non-entry preamble and its flat,
    alphabetized list of entries."""

    preamble: str
    entries: list[GlossaryEntry]
    trailing_newline: bool

    def by_term_lower(self) -> dict[str, GlossaryEntry]:
        return {entry.term.lower(): entry for entry in self.entries}

    def render(self) -> str:
        if not self.entries:
            # Nothing to reflow; the preamble already carries the original
            # text byte-for-byte, including its trailing-newline state.
            return self.preamble
        preamble = self.preamble
        # Convention: exactly one blank line separates the header (and its
        # trailing `---` separator, when present) from the first entry.
        if preamble and not preamble.endswith("\n\n"):
            preamble = preamble.rstrip("\n") + "\n\n"
        body = "\n".join(entry.render() for entry in self.entries)
        text = preamble + body
        if self.trailing_newline:
            text += "\n"
        return text


class GlossaryValidationError(ValueError):
    pass


def parse_glossary(text: str) -> ParsedGlossary:
    """Split ``text`` into preamble and entries, and validate the entry
    section's grammar and alphabetical order. Raises ``GlossaryValidationError``
    if any bullet line is malformed or if the entries are not alphabetized.

    The header may itself contain example bullet lines (illustrating the
    entry grammar) before a standalone ``---`` separator; those examples are
    not part of the flat alphabetized term list. Only bullets after the last
    standalone ``---`` line are treated as real entries. A glossary with no
    such separator treats every top-level bullet as a real entry.
    """

    lines = text.splitlines(keepends=True)

    separator_index = None
    for index, line in enumerate(lines):
        if line.strip() == SEPARATOR_LINE:
            separator_index = index

    search_from = separator_index + 1 if separator_index is not None else 0

    entry_start = None
    for index in range(search_from, len(lines)):
        if lines[index].startswith("- **"):
            entry_start = index
            break

    if entry_start is None:
        # No real entries yet (only header text and, optionally, header
        # example bullets before the separator); the whole text is preamble.
        return ParsedGlossary(preamble=text, entries=[], trailing_newline=text.endswith("\n"))

    preamble = "".join(lines[:entry_start])
    entry_lines = lines[entry_start:]
    trailing_newline = text.endswith("\n")

    entries: list[GlossaryEntry] = []
    for line in entry_lines:
        stripped = line.rstrip("\n").rstrip("\r")
        if not stripped.strip():
            raise GlossaryValidationError("blank line within the flat entry list")
        entry = parse_entry_line(stripped)
        if entry is None:
            raise GlossaryValidationError(f"malformed glossary entry: {stripped!r}")
        entries.append(entry)

    lowered = [entry.term.lower() for entry in entries]
    if lowered != sorted(lowered):
        raise GlossaryValidationError("glossary entries are not alphabetized")

    return ParsedGlossary(preamble=preamble, entries=entries, trailing_newline=trailing_newline)


def validate_glossary(text: str) -> None:
    parse_glossary(text)


# ---------------------------------------------------------------------------
# Transcript parsing: operator-message-only extraction
# ---------------------------------------------------------------------------

# Synthetic Claude Code wrapper payloads that are never operator prose, even
# though they arrive as `type: "user"` transcript lines.
_CLAUDE_SYNTHETIC_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<task-notification>",
    "<local-command-stdout>",
    "<local-command-stderr>",
)


def _claude_message_is_operator(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta"):
        return False
    if entry.get("isSidechain"):
        return False
    origin = entry.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
        return False
    prompt_source = entry.get("promptSource")
    if prompt_source == "system":
        return False
    return True


def _claude_message_text(entry: dict) -> str:
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = "\n".join(parts)
    else:
        return ""
    stripped = text.strip()
    if any(stripped.startswith(prefix) for prefix in _CLAUDE_SYNTHETIC_PREFIXES):
        return ""
    return text


def extract_operator_messages_claude(transcript_text: str) -> list[str]:
    """Parse a Claude Code JSONL transcript and return operator-authored
    message texts in transcript order. Non-JSON lines are skipped."""

    messages: list[str] = []
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(entry, dict):
            continue
        if not _claude_message_is_operator(entry):
            continue
        text = _claude_message_text(entry)
        if text.strip():
            messages.append(text)
    return messages


def _opencode_messages_list(payload) -> list:
    if isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            return payload["messages"]
        if isinstance(payload.get("data"), list):
            return payload["data"]
        return []
    if isinstance(payload, list):
        return payload
    return []


def extract_operator_messages_opencode(payload) -> list[str]:
    """Parse an Opencode message list (as returned by
    ``client.session.messages()`` or ``opencode export``) and return
    operator-authored message texts in order. Synthetic text parts (for
    example an auto-continue turn after compaction) are excluded."""

    messages: list[str] = []
    for message in _opencode_messages_list(payload):
        if not isinstance(message, dict):
            continue
        info = message.get("info")
        if not isinstance(info, dict) or info.get("role") != "user":
            continue
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        texts = [
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
            and part.get("type") == "text"
            and not part.get("synthetic")
        ]
        text = "\n".join(t for t in texts if t.strip())
        if text.strip():
            messages.append(text)
    return messages


def sniff_and_extract(raw_text: str) -> list[str]:
    """Best-effort format detection between a Claude Code JSONL transcript
    and an Opencode JSON message payload, for callers that do not know the
    source ahead of time."""

    stripped = raw_text.strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        try:
            payload = json.loads(stripped)
        except (ValueError, TypeError):
            payload = None
        if payload is not None:
            messages = extract_operator_messages_opencode(payload)
            if messages:
                return messages
            # Fall through to JSONL parsing in case of an ambiguous single
            # JSON object that also happens to be a one-line transcript.
    return extract_operator_messages_claude(raw_text)


# ---------------------------------------------------------------------------
# Candidate extraction rules
# ---------------------------------------------------------------------------

DEFAULT_MIN_REPETITIONS = 3

_TERM = r"[a-zA-Z][a-zA-Z0-9 _-]{1,40}?"

# Portability gate: deterministically reject candidates whose term or meaning
# names them as scoped to one specific codebase, rather than portable
# operator meta-language whose meaning survives moving to another repo (the
# issue's explicit non-goal — project-specific vocabulary belongs in that
# repo's own CONTEXT.md, not the personal glossary). This is a fixed phrase
# check, not an LLM judgment call: any explicit self-scoping reference such
# as "this repo(sitory)", "this codebase", "this project", or the "our"
# equivalent, anywhere in the term or meaning, disqualifies the candidate
# even when every other extraction rule (correction, alias, definition,
# repetition) would otherwise accept it.
_PROJECT_SCOPE_RE = re.compile(
    r"\b(?:this|our|the current)\s+"
    r"(?:repo|repository|codebase|monorepo|project|application|app|service|workspace)\b",
    re.IGNORECASE,
)

# Companion patterns for self-scoping phrasings that don't fit the
# "this/our/the current <noun>" shape above: an explicit "unique/specific/
# proprietary to <name-or-scope>" or "only used/defined/exists in <scope>"
# reference is just as much a portability disqualifier, whether the scope is
# a generic noun ("this workspace") or a proper noun ("Acme", "FooCorp").
_PROJECT_SCOPE_PHRASE_RE = re.compile(
    r"\b(?:"
    r"unique to (?:this|our|the)\s+[a-z0-9_-]+"
    r"|specific to\s+[a-z][\w-]*"
    r"|proprietary to\s+[a-z][\w-]*"
    r"|only (?:used|defined|exists) in (?:this|our|the)\s+[a-z0-9_-]+"
    r")\b",
    re.IGNORECASE,
)


def _is_portable(term: str, meaning: str) -> bool:
    for text in (term, meaning):
        if _PROJECT_SCOPE_RE.search(text) or _PROJECT_SCOPE_PHRASE_RE.search(text):
            return False
    return True


_CORRECTION_PATTERNS = [
    re.compile(
        rf"\b(?:i say|i use|call it|we call it|the term is)\s+"
        rf"[\"“]?(?P<term>{_TERM})[\"”]?\s*,?\s*not\s+"
        rf"[\"“]?(?P<anti>{_TERM})[\"”]?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bnot\s+[\"“]?(?P<anti>{_TERM})[\"”]?\s*[,;]\s*"
        rf"(?:i say|i use|call it|we call it|the term is)\s+"
        rf"[\"“]?(?P<term>{_TERM})[\"”]?[.!]?$",
        re.IGNORECASE,
    ),
]

_ALIAS_PATTERNS = [
    re.compile(
        rf"[\"“]?(?P<term>{_TERM})[\"”]?\s+(?:is|are)\s+"
        rf"(?:also known as|an alias for|aka)\s+"
        rf"[\"“]?(?P<alias>{_TERM})[\"”]?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"[\"“]?(?P<term>{_TERM})[\"”]?\s*,\s*aka\s+"
        rf"[\"“]?(?P<alias>{_TERM})[\"”]?[.!]?$",
        re.IGNORECASE,
    ),
]

_DEFINITION_PATTERNS = [
    re.compile(
        rf"\bdefine\s+[\"“]?(?P<term>{_TERM})[\"”]?\s+as\s+"
        rf"(?P<meaning>.{{5,200}}?)[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"[\"“]?(?P<term>{_TERM})[\"”]?\s+means\s+"
        rf"(?P<meaning>.{{5,200}}?)[.!]?$",
        re.IGNORECASE,
    ),
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be
    because been before being below between both but by can't cannot could
    couldn't did didn't do does doesn't doing don't down during each few for
    from further had hadn't has hasn't have haven't having he he'd he'll
    he's her here here's hers herself him himself his how how's i i'd i'll
    i'm i've if in into is isn't it it's its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our ours
    ourselves out over own same shan't she she'd she'll she's should
    shouldn't so some such than that that's the their theirs them themselves
    then there there's these they they'd they'll they're they've this those
    through to too under until up very was wasn't we we'd we'll we're we've
    were weren't what what's when when's where where's which while who who's
    whom why why's with won't would wouldn't you you'd you'll you're you've
    your yours yourself yourselves also just like really quite kind sort
    thing things want wants wanted need needs needed get gets got make makes
    made say says said use uses used using one two lot bit way ways going go
    goes went
    """.split()
)

COMMON_PROGRAMMING_KEYWORDS = frozenset(
    """
    function variable class method return import export const let var def
    self print true false null none string number boolean array object list
    dict set tuple file files code test tests bug bugs error errors commit
    branch repo repository git python javascript typescript node npm bash
    shell script scripts run runs running build builds api json yaml config
    data value values type types module modules package packages
    """.split()
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z][a-zA-Z0-9'-]*", text.lower())


def _split_sentences(message: str) -> list[str]:
    sentences = []
    for chunk in message.splitlines():
        chunk = chunk.strip()
        if not chunk:
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(chunk):
            sentence = sentence.strip()
            if sentence:
                sentences.append(sentence)
    return sentences


@dataclass
class Candidate:
    term: str
    meaning: str
    kind: str  # "correction" | "alias" | "definition" | "repeated"
    evidence: str
    not_terms: tuple[str, ...] = ()
    aka_terms: tuple[str, ...] = ()
    frequency: int = 1


def _normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().strip("\"'“”"))


def _clean_meaning(meaning: str) -> str:
    meaning = re.sub(r"\s+", " ", meaning.strip().strip("\"'“”"))
    if meaning and meaning[-1] not in ".!?":
        meaning += "."
    return meaning


# When one term collects evidence of more than one explicit kind (a
# correction, an alias, and a definition all naming the same term), the
# merged candidate keeps the strongest available explicit meaning. A real
# operator-authored definition is always more informative than a meaning
# synthesized from a correction's anti-term or an alias's alternate name.
_EXPLICIT_KIND_PRIORITY = {"definition": 3, "correction": 2, "alias": 1}


def _dedupe_preserve_order(items: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate case-insensitively while keeping first-seen order and
    casing, for deterministic accumulated not-term/alias lists."""

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)


@dataclass
class _ExplicitMatch:
    term: str
    kind: str
    meaning: str
    evidence: str
    not_terms: tuple[str, ...] = ()
    aka_terms: tuple[str, ...] = ()


def _extract_explicit_candidates(messages: Iterable[str]) -> list[Candidate]:
    """Extract one merged candidate per distinct term named by an explicit
    correction, alias, and/or definition statement.

    A term can accumulate more than one kind of explicit evidence across the
    operator's messages (for example a correction, then later an alias, then
    later a definition, all naming the same canonical term). Every match is
    kept: unique anti-terms and aliases accumulate in first-seen order and
    are deduplicated case-insensitively, and the merged candidate's meaning
    and ``kind`` come from the single strongest explicit statement
    (definition, then correction, then alias) rather than only the first
    pattern that happened to match.
    """

    matches: dict[str, list[_ExplicitMatch]] = {}

    def _record(term: str, kind: str, meaning: str, evidence: str, **extra) -> None:
        key = term.lower()
        matches.setdefault(key, []).append(
            _ExplicitMatch(term=term, kind=kind, meaning=meaning, evidence=evidence, **extra)
        )

    for message in messages:
        for sentence in _split_sentences(message):
            for pattern in _CORRECTION_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                anti = _normalize_term(match.group("anti"))
                _record(
                    term,
                    "correction",
                    f"the operator's canonical term for {anti.lower()}.",
                    sentence,
                    not_terms=(anti,),
                )
            for pattern in _ALIAS_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                alias = _normalize_term(match.group("alias"))
                _record(
                    term,
                    "alias",
                    f"also called {alias.lower()} by the operator.",
                    sentence,
                    aka_terms=(alias,),
                )
            for pattern in _DEFINITION_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                meaning = _clean_meaning(match.group("meaning"))
                _record(term, "definition", meaning, sentence)

    candidates: list[Candidate] = []
    for entries in matches.values():
        # First-seen casing of the term is the canonical rendering.
        term = entries[0].term
        best = max(entries, key=lambda entry: _EXPLICIT_KIND_PRIORITY[entry.kind])
        not_terms = _dedupe_preserve_order(
            anti for entry in entries for anti in entry.not_terms
        )
        aka_terms = _dedupe_preserve_order(
            alias for entry in entries for alias in entry.aka_terms
        )
        candidates.append(
            Candidate(
                term=term,
                meaning=best.meaning,
                kind=best.kind,
                evidence=best.evidence,
                not_terms=not_terms,
                aka_terms=aka_terms,
            )
        )
    return candidates


_DEFINITION_CONNECTOR_RE = re.compile(r"\b(is|are|means|refers to|when)\b", re.IGNORECASE)

# A meaning clause counts as a real definition only when it reads like a
# noun-phrase description ("is a full replay of...", "is where I keep...",
# "is my term for...") rather than a transient state or generic adjective
# ("is broken", "is real again", "is small"). This keeps a merely frequent
# term out of the glossary when the operator never actually explains it.
_DEFINITIONAL_MEANING_RE = re.compile(
    r"^(a|an|the|my|our|your|someone's|something|where|when|how|what)\b",
    re.IGNORECASE,
)


def _infer_meaning_for_term(term: str, messages: Iterable[str]) -> Optional[tuple[str, str]]:
    """Return ``(meaning, evidence_sentence)`` for a repeated term, or
    ``None`` when no operator sentence supports a meaningful one-line
    definition (ambiguity rejection)."""

    term_re = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    for message in messages:
        for sentence in _split_sentences(message):
            if not term_re.search(sentence):
                continue
            if not _DEFINITION_CONNECTOR_RE.search(sentence):
                continue
            word_count = len(sentence.split())
            if word_count < 4 or word_count > 40:
                continue
            rest_match = re.search(
                r"\b"
                + re.escape(term)
                + r"\b\s*(?:is|are|means|refers to)\s+(?P<rest>.+)$",
                sentence,
                re.IGNORECASE,
            )
            if not rest_match:
                # No isolatable meaning clause (for example the connector
                # was "when", which reads as a usage example rather than a
                # definition) - not enough to support a one-line meaning.
                continue
            meaning = _clean_meaning(rest_match.group("rest"))
            if len(meaning.split()) < 3:
                continue
            if not _DEFINITIONAL_MEANING_RE.search(meaning):
                # Reads like a state or adjective ("is broken", "is small",
                # "is real again"), not a definition. Ambiguity rejection.
                continue
            return meaning, sentence
    return None


def _extract_repeated_candidates(
    messages: list[str], min_repetitions: int
) -> list[Candidate]:
    unigram_messages: dict[str, set[int]] = {}
    bigram_messages: dict[str, set[int]] = {}

    tokenized = [_tokenize(message) for message in messages]

    for index, tokens in enumerate(tokenized):
        seen_unigrams = set()
        seen_bigrams = set()
        for token in tokens:
            if len(token) < 4:
                continue
            if token in STOPWORDS or token in COMMON_PROGRAMMING_KEYWORDS:
                continue
            seen_unigrams.add(token)
        for first, second in zip(tokens, tokens[1:]):
            if first in STOPWORDS or second in STOPWORDS:
                continue
            if first in COMMON_PROGRAMMING_KEYWORDS or second in COMMON_PROGRAMMING_KEYWORDS:
                continue
            if len(first) < 3 or len(second) < 3:
                continue
            seen_bigrams.add(f"{first} {second}")
        for term in seen_unigrams:
            unigram_messages.setdefault(term, set()).add(index)
        for term in seen_bigrams:
            bigram_messages.setdefault(term, set()).add(index)

    candidates: list[Candidate] = []
    seen_terms: set[str] = set()

    # Prefer bigrams over their constituent unigrams: a qualifying phrase is
    # more precise than either of its component words.
    for term, indices in sorted(bigram_messages.items()):
        if len(indices) < min_repetitions:
            continue
        inferred = _infer_meaning_for_term(term, messages)
        if inferred is None:
            continue
        meaning, evidence = inferred
        candidates.append(
            Candidate(
                term=term,
                meaning=meaning,
                kind="repeated",
                evidence=evidence,
                frequency=len(indices),
            )
        )
        seen_terms.add(term)
        for word in term.split():
            seen_terms.add(word)

    for term, indices in sorted(unigram_messages.items()):
        if term in seen_terms:
            continue
        if len(indices) < min_repetitions:
            continue
        inferred = _infer_meaning_for_term(term, messages)
        if inferred is None:
            continue
        meaning, evidence = inferred
        candidates.append(
            Candidate(
                term=term,
                meaning=meaning,
                kind="repeated",
                evidence=evidence,
                frequency=len(indices),
            )
        )

    return candidates


def find_candidates(
    messages: list[str], min_repetitions: int = DEFAULT_MIN_REPETITIONS
) -> list[Candidate]:
    """Find deterministic curation candidates across operator ``messages``.

    Explicit corrections, aliases, and definitions are always considered.
    Distinctive repeated terms are considered only once they clear
    ``min_repetitions`` distinct operator messages, after stopword and
    common-programming-keyword filtering, and only when a supporting
    operator sentence yields a meaningful one-line inferred meaning.

    Every candidate — explicit or repeated — then passes a portability gate:
    a term or meaning that explicitly scopes itself to one codebase (for
    example "unique to this repository") is rejected outright, even when it
    was stated as an explicit correction/alias/definition. Project-specific
    vocabulary belongs in that repo's own CONTEXT.md, never the personal
    glossary.
    """

    explicit = _extract_explicit_candidates(messages)
    explicit_terms = {candidate.term.lower() for candidate in explicit}

    repeated = [
        candidate
        for candidate in _extract_repeated_candidates(messages, min_repetitions)
        if candidate.term.lower() not in explicit_terms
    ]

    return [
        candidate
        for candidate in explicit + repeated
        if _is_portable(candidate.term, candidate.meaning)
    ]


# ---------------------------------------------------------------------------
# Applying candidates to the canonical glossary
# ---------------------------------------------------------------------------


@dataclass
class AppliedChange:
    term: str
    meaning: str


def _refine_existing_entry(
    entry: GlossaryEntry, candidate: Candidate
) -> Optional[str]:
    """Merge a candidate's new metadata into an already-existing unlocked
    entry in place. Returns the resulting meaning when something actually
    changed (and thus qualifies as an applied refinement), or ``None`` when
    the candidate carried nothing the entry didn't already have.

    Enriching an existing unlocked entry with new alias/anti-term metadata,
    or a stronger explicit meaning, is not "adding a duplicate" — the issue's
    duplicate-avoidance rule is about never writing a second entry for a term
    that already exists, not about refusing to improve the one entry that's
    already there. A locked entry is never passed to this function.
    """

    merged_not_terms = _dedupe_preserve_order((*entry.not_terms, *candidate.not_terms))
    merged_aka_terms = _dedupe_preserve_order((*entry.aka_terms, *candidate.aka_terms))

    # Only an explicit definition is unambiguously stronger than whatever
    # meaning the entry already carries (hand-written, or from an earlier
    # correction/alias/repeated candidate). Per `_EXPLICIT_KIND_PRIORITY`,
    # definition outranks both correction and alias, and a merely "repeated"
    # candidate carries no explicit meaning strong enough to override text
    # already in the glossary.
    new_meaning = entry.meaning
    if candidate.kind == "definition" and candidate.meaning != entry.meaning:
        new_meaning = candidate.meaning

    changed = (
        merged_not_terms != entry.not_terms
        or merged_aka_terms != entry.aka_terms
        or new_meaning != entry.meaning
    )
    if not changed:
        return None

    entry.not_terms = merged_not_terms
    entry.aka_terms = merged_aka_terms
    entry.meaning = new_meaning
    return new_meaning


def apply_candidates(
    text: str, candidates: Iterable[Candidate]
) -> tuple[str, list[AppliedChange]]:
    """Apply qualifying candidates to the canonical glossary text.

    A term with no existing entry is inserted as a new unlocked entry. A
    term that already has an unlocked entry is refined in place — new
    not-terms/aka-terms merge in (deduplicated case-insensitively, first-seen
    order preserved) and the meaning is updated when the candidate supplies a
    stronger explicit one — rather than being skipped outright; a refinement
    that changes nothing real is skipped as a no-op duplicate. A locked entry
    is never modified. Never deletes anything. Returns the complete updated
    glossary text (already re-alphabetized) and the list of changes actually
    applied, in the order they were applied.
    """

    parsed = parse_glossary(text)
    entries_by_lower = {entry.term.lower(): entry for entry in parsed.entries}

    applied: list[AppliedChange] = []
    new_entries = list(parsed.entries)

    for candidate in candidates:
        key = candidate.term.lower()
        existing = entries_by_lower.get(key)

        if existing is None:
            entry = GlossaryEntry(
                term=candidate.term,
                meaning=candidate.meaning,
                locked=False,
                not_terms=candidate.not_terms,
                aka_terms=candidate.aka_terms,
            )
            new_entries.append(entry)
            entries_by_lower[key] = entry
            applied.append(AppliedChange(term=candidate.term, meaning=candidate.meaning))
            continue

        if existing.locked:
            continue

        refined_meaning = _refine_existing_entry(existing, candidate)
        if refined_meaning is None:
            continue
        applied.append(AppliedChange(term=existing.term, meaning=refined_meaning))

    new_entries.sort(key=lambda entry: entry.term.lower())
    updated = ParsedGlossary(
        preamble=parsed.preamble,
        entries=new_entries,
        trailing_newline=parsed.trailing_newline,
    )
    updated_text = updated.render()
    # Validate the complete proposed content before returning it so callers
    # never write invalid grammar or ordering.
    validate_glossary(updated_text)
    return updated_text, applied
