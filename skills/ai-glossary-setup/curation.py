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


@dataclass
class GlossaryEntry:
    term: str
    meaning: str
    locked: bool = False
    not_terms: tuple[str, ...] = ()
    aka_terms: tuple[str, ...] = ()

    def render(self) -> str:
        flags = []
        if self.locked:
            flags.append("locked")
        if self.not_terms:
            flags.append("not: " + ", ".join(self.not_terms))
        if self.aka_terms:
            flags.append("aka: " + ", ".join(self.aka_terms))
        suffix = f" *({'; '.join(flags)})*" if flags else ""
        return f"- **{self.term}** — {self.meaning}{suffix}"


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
    return GlossaryEntry(
        term=match.group("term"),
        meaning=match.group("meaning"),
        locked=locked,
        not_terms=not_terms,
        aka_terms=aka_terms,
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


def _extract_explicit_candidates(messages: Iterable[str]) -> list[Candidate]:
    candidates: dict[str, Candidate] = {}
    for message in messages:
        for sentence in _split_sentences(message):
            for pattern in _CORRECTION_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                anti = _normalize_term(match.group("anti"))
                key = term.lower()
                if key not in candidates:
                    candidates[key] = Candidate(
                        term=term,
                        meaning=f"the operator's canonical term for {anti.lower()}.",
                        kind="correction",
                        evidence=sentence,
                        not_terms=(anti,),
                    )
            for pattern in _ALIAS_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                alias = _normalize_term(match.group("alias"))
                key = term.lower()
                if key not in candidates:
                    candidates[key] = Candidate(
                        term=term,
                        meaning=f"also called {alias.lower()} by the operator.",
                        kind="alias",
                        evidence=sentence,
                        aka_terms=(alias,),
                    )
            for pattern in _DEFINITION_PATTERNS:
                match = pattern.search(sentence)
                if not match:
                    continue
                term = _normalize_term(match.group("term"))
                meaning = _clean_meaning(match.group("meaning"))
                key = term.lower()
                if key not in candidates:
                    candidates[key] = Candidate(
                        term=term,
                        meaning=meaning,
                        kind="definition",
                        evidence=sentence,
                    )
    return list(candidates.values())


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
    """

    explicit = _extract_explicit_candidates(messages)
    explicit_terms = {candidate.term.lower() for candidate in explicit}

    repeated = [
        candidate
        for candidate in _extract_repeated_candidates(messages, min_repetitions)
        if candidate.term.lower() not in explicit_terms
    ]

    return explicit + repeated


# ---------------------------------------------------------------------------
# Applying candidates to the canonical glossary
# ---------------------------------------------------------------------------


@dataclass
class AppliedChange:
    term: str
    meaning: str


def apply_candidates(
    text: str, candidates: Iterable[Candidate]
) -> tuple[str, list[AppliedChange]]:
    """Insert qualifying candidates into the canonical glossary text.

    Never modifies an existing entry: a term that already exists (locked or
    not) is skipped as a duplicate. Never deletes anything. Returns the
    complete updated glossary text (already re-alphabetized) and the list of
    changes actually applied, in the order they were applied.
    """

    parsed = parse_glossary(text)
    existing_lower = {entry.term.lower() for entry in parsed.entries}

    applied: list[AppliedChange] = []
    new_entries = list(parsed.entries)

    for candidate in candidates:
        key = candidate.term.lower()
        if key in existing_lower:
            continue
        entry = GlossaryEntry(
            term=candidate.term,
            meaning=candidate.meaning,
            locked=False,
            not_terms=candidate.not_terms,
            aka_terms=candidate.aka_terms,
        )
        new_entries.append(entry)
        existing_lower.add(key)
        applied.append(AppliedChange(term=candidate.term, meaning=candidate.meaning))

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
