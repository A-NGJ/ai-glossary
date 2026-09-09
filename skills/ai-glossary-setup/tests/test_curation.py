#!/usr/bin/env python3
"""Unit tests for the deterministic automatic-curation engine.

Covers, per the issue's Testing Decisions: explicit corrections, aliases,
definitions, operator-message-only filtering, frequency filtering, stopword
exclusion, contextual inference, ambiguity rejection, duplicate avoidance,
locked-term protection, grammar validation, ordering, and glossary rendering.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "curation.py"
SPEC = importlib.util.spec_from_file_location("ai_glossary_curation", SCRIPT)
curation = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.path.insert(0, str(SKILL_DIR))
sys.modules[SPEC.name] = curation
SPEC.loader.exec_module(curation)


TEMPLATE_TEXT = (SKILL_DIR / "templates" / "glossary.md").read_text(encoding="utf-8")

POPULATED_GLOSSARY = (
    "# Personal Glossary\n\n"
    "Header text.\n\n"
    "Entry grammar — one line per term, flat and alphabetized:\n"
    "`- **term** — one-line meaning. *(locked; not: anti-term, …; aka: alias, …)*`\n\n"
    "Examples of good entries:\n\n"
    "- **ubiquitous language** — one shared vocabulary. *(locked)*\n\n"
    "---\n\n"
    "- **alpha** — first term.\n"
    "- **charlie** — third term. *(locked)*\n"
)


class GlossaryGrammarTest(unittest.TestCase):
    def test_parse_entry_line_round_trips_all_flag_kinds(self):
        line = "- **term** — one-line meaning. *(locked; not: anti-term, other; aka: alias, other-alias)*"
        entry = curation.parse_entry_line(line)
        self.assertEqual(entry.term, "term")
        self.assertEqual(entry.meaning, "one-line meaning.")
        self.assertTrue(entry.locked)
        self.assertEqual(entry.not_terms, ("anti-term", "other"))
        self.assertEqual(entry.aka_terms, ("alias", "other-alias"))
        self.assertEqual(entry.render(), line)

    def test_parse_entry_line_without_flags(self):
        line = "- **term** — plain meaning."
        entry = curation.parse_entry_line(line)
        self.assertFalse(entry.locked)
        self.assertEqual(entry.not_terms, ())
        self.assertEqual(entry.aka_terms, ())
        self.assertEqual(entry.render(), line)

    def test_parse_entry_line_rejects_malformed_bullet(self):
        self.assertIsNone(curation.parse_entry_line("- missing bold markers"))
        self.assertIsNone(curation.parse_entry_line("* **term** — wrong bullet char."))

    def test_parse_glossary_excludes_header_example_bullets_before_separator(self):
        parsed = curation.parse_glossary(POPULATED_GLOSSARY)
        terms = [entry.term for entry in parsed.entries]
        self.assertNotIn("ubiquitous language", terms)
        self.assertEqual(terms, ["alpha", "charlie"])

    def test_parse_glossary_round_trips_populated_glossary_byte_for_byte(self):
        parsed = curation.parse_glossary(POPULATED_GLOSSARY)
        self.assertEqual(parsed.render(), POPULATED_GLOSSARY)

    def test_parse_glossary_round_trips_template_with_no_real_entries(self):
        parsed = curation.parse_glossary(TEMPLATE_TEXT)
        self.assertEqual(parsed.entries, [])
        self.assertEqual(parsed.render(), TEMPLATE_TEXT)

    def test_parse_glossary_rejects_out_of_order_entries(self):
        text = "---\n\n- **zebra** — z.\n- **alpha** — a.\n"
        with self.assertRaises(curation.GlossaryValidationError):
            curation.parse_glossary(text)

    def test_parse_glossary_rejects_malformed_entry_line(self):
        text = "---\n\n- **alpha** — a.\nnot a bullet at all\n"
        with self.assertRaises(curation.GlossaryValidationError):
            curation.parse_glossary(text)

    def test_validate_glossary_accepts_valid_text_and_raises_on_invalid(self):
        curation.validate_glossary(POPULATED_GLOSSARY)
        with self.assertRaises(curation.GlossaryValidationError):
            curation.validate_glossary("---\n\n- **b** — x.\n- **a** — y.\n")


class LeadingLockSyntaxTest(unittest.TestCase):
    """Per the template header, a lock may be rendered either as the
    `locked` flag or as a leading 🔒 before the term
    (`- **🔒 anchor** — ...`). Both must be recognized as lock metadata, not
    term text, so the canonicalized term matches a plain-text candidate and
    stays protected from autonomous duplication/revision."""

    def test_leading_lock_glyph_is_recognized_as_locked_not_term_text(self):
        entry = curation.parse_entry_line("- **🔒 anchor** — original wording.")
        self.assertEqual(entry.term, "anchor")
        self.assertTrue(entry.locked)

    def test_leading_lock_glyph_round_trips_byte_for_byte(self):
        line = "- **🔒 anchor** — original wording."
        entry = curation.parse_entry_line(line)
        self.assertEqual(entry.render(), line)

    def test_leading_lock_glyph_glossary_round_trips_byte_for_byte(self):
        text = "---\n\n- **🔒 anchor** — original wording.\n"
        parsed = curation.parse_glossary(text)
        self.assertEqual(parsed.render(), text)

    def test_leading_lock_glyph_prevents_duplicate_unlocked_candidate(self):
        glossary = "---\n\n- **🔒 anchor** — original wording.\n"
        candidates = [
            curation.Candidate(
                term="anchor", meaning="a hostile rewrite.", kind="repeated", evidence=""
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, glossary)

    def test_leading_lock_glyph_matches_case_insensitively(self):
        glossary = "---\n\n- **🔒 Anchor** — original wording.\n"
        candidates = [
            curation.Candidate(
                term="ANCHOR", meaning="a hostile rewrite.", kind="repeated", evidence=""
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, glossary)

    def test_locked_flag_and_leading_glyph_both_report_locked(self):
        flag_locked = curation.parse_entry_line("- **term** — meaning. *(locked)*")
        glyph_locked = curation.parse_entry_line("- **🔒 term** — meaning.")
        self.assertTrue(flag_locked.locked)
        self.assertTrue(glyph_locked.locked)
        self.assertFalse(flag_locked.locked_prefix)
        self.assertTrue(glyph_locked.locked_prefix)


class ClaudeTranscriptExtractionTest(unittest.TestCase):
    @staticmethod
    def _line(**fields):
        return json.dumps(fields)

    def test_extracts_plain_operator_message(self):
        transcript = self._line(
            type="user", message={"role": "user", "content": "hello operator"}
        )
        self.assertEqual(
            curation.extract_operator_messages_claude(transcript), ["hello operator"]
        )

    def test_extracts_text_parts_from_list_content(self):
        transcript = self._line(
            type="user",
            message={
                "role": "user",
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "tool_result", "text": "ignored"},
                    {"type": "text", "text": "part two"},
                ],
            },
        )
        messages = curation.extract_operator_messages_claude(transcript)
        self.assertEqual(messages, ["part one\npart two"])

    def test_excludes_assistant_messages(self):
        transcript = self._line(
            type="assistant", message={"role": "assistant", "content": "agent text"}
        )
        self.assertEqual(curation.extract_operator_messages_claude(transcript), [])

    def test_excludes_meta_and_sidechain_messages(self):
        lines = "\n".join(
            [
                self._line(
                    type="user",
                    isMeta=True,
                    message={"role": "user", "content": "meta stuff"},
                ),
                self._line(
                    type="user",
                    isSidechain=True,
                    message={"role": "user", "content": "sidechain stuff"},
                ),
            ]
        )
        self.assertEqual(curation.extract_operator_messages_claude(lines), [])

    def test_excludes_non_human_origin_and_system_prompt_source(self):
        lines = "\n".join(
            [
                self._line(
                    type="user",
                    origin={"kind": "task-notification"},
                    message={"role": "user", "content": "from a task"},
                ),
                self._line(
                    type="user",
                    promptSource="system",
                    message={"role": "user", "content": "system generated"},
                ),
            ]
        )
        self.assertEqual(curation.extract_operator_messages_claude(lines), [])

    def test_excludes_synthetic_command_wrapper_text(self):
        lines = "\n".join(
            [
                self._line(
                    type="user",
                    message={
                        "role": "user",
                        "content": "<command-name>/clear</command-name>",
                    },
                ),
                self._line(
                    type="user",
                    message={
                        "role": "user",
                        "content": "<task-notification>done</task-notification>",
                    },
                ),
            ]
        )
        self.assertEqual(curation.extract_operator_messages_claude(lines), [])

    def test_skips_non_json_and_non_object_lines(self):
        lines = "\n".join(["not json at all", "[1, 2, 3]", ""])
        self.assertEqual(curation.extract_operator_messages_claude(lines), [])

    def test_preserves_transcript_order_across_multiple_messages(self):
        lines = "\n".join(
            [
                self._line(type="user", message={"role": "user", "content": "first"}),
                self._line(
                    type="assistant", message={"role": "assistant", "content": "reply"}
                ),
                self._line(type="user", message={"role": "user", "content": "second"}),
            ]
        )
        self.assertEqual(
            curation.extract_operator_messages_claude(lines), ["first", "second"]
        )


class OpencodeMessageExtractionTest(unittest.TestCase):
    def test_extracts_user_text_parts(self):
        payload = {
            "messages": [
                {
                    "info": {"role": "user"},
                    "parts": [{"type": "text", "text": "operator says hi"}],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [{"type": "text", "text": "agent reply"}],
                },
            ]
        }
        self.assertEqual(
            curation.extract_operator_messages_opencode(payload), ["operator says hi"]
        )

    def test_excludes_synthetic_text_parts(self):
        payload = {
            "messages": [
                {
                    "info": {"role": "user"},
                    "parts": [
                        {"type": "text", "text": "synthetic continue", "synthetic": True}
                    ],
                }
            ]
        }
        self.assertEqual(curation.extract_operator_messages_opencode(payload), [])

    def test_excludes_non_text_parts(self):
        payload = {
            "messages": [
                {
                    "info": {"role": "user"},
                    "parts": [{"type": "tool", "text": "ignored"}],
                }
            ]
        }
        self.assertEqual(curation.extract_operator_messages_opencode(payload), [])

    def test_accepts_bare_list_payload(self):
        payload = [
            {
                "info": {"role": "user"},
                "parts": [{"type": "text", "text": "bare list form"}],
            }
        ]
        self.assertEqual(
            curation.extract_operator_messages_opencode(payload), ["bare list form"]
        )

    def test_accepts_data_wrapped_payload_from_sdk_response(self):
        payload = {
            "data": [
                {
                    "info": {"role": "user"},
                    "parts": [{"type": "text", "text": "sdk wrapped"}],
                }
            ]
        }
        self.assertEqual(
            curation.extract_operator_messages_opencode(payload), ["sdk wrapped"]
        )


class ExplicitCandidateRuleTest(unittest.TestCase):
    def test_correction_pattern_i_say_x_not_y(self):
        candidates = curation.find_candidates(
            ["I say fog of war, not blocked scope."]
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.term, "fog of war")
        self.assertEqual(candidate.kind, "correction")
        self.assertEqual(candidate.not_terms, ("blocked scope",))

    def test_correction_pattern_not_y_i_say_x(self):
        candidates = curation.find_candidates(
            ["Not blocked scope, I say fog of war."]
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].term, "fog of war")
        self.assertEqual(candidates[0].not_terms, ("blocked scope",))

    def test_alias_pattern_is_also_known_as(self):
        candidates = curation.find_candidates(
            ["Session compaction is also known as context pruning."]
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.term, "Session compaction")
        self.assertEqual(candidate.kind, "alias")
        self.assertEqual(candidate.aka_terms, ("context pruning",))

    def test_alias_pattern_comma_aka(self):
        candidates = curation.find_candidates(["Fog of war, aka fog."])
        terms = {c.term.lower(): c for c in candidates}
        self.assertIn("fog of war", terms)
        self.assertEqual(terms["fog of war"].aka_terms, ("fog",))

    def test_definition_pattern_define_x_as(self):
        candidates = curation.find_candidates(
            [
                "Define trajectory audit as a full replay of an agent run to "
                "find where it drifted."
            ]
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.term, "trajectory audit")
        self.assertEqual(candidate.kind, "definition")
        self.assertIn("full replay", candidate.meaning)

    def test_definition_pattern_x_means_y(self):
        candidates = curation.find_candidates(
            ["Context rot means the decay of reasoning quality over a long session."]
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].term, "Context rot")
        self.assertEqual(candidates[0].kind, "definition")

    def test_explicit_candidates_do_not_require_repetition(self):
        # A single mention is enough for an explicit correction/alias/definition,
        # unlike the repeated-term rule.
        candidates = curation.find_candidates(["I say wayfinder, not roadmap."])
        self.assertEqual(len(candidates), 1)


class CombinedExplicitEvidenceTest(unittest.TestCase):
    """Multiple operator statements naming the same canonical term — a
    correction, an alias, and a definition — must merge into one candidate
    that keeps the strongest explicit meaning plus every accumulated unique
    anti-term and alias, rather than collapsing to only the first pattern
    that matched."""

    def test_correction_alias_and_definition_for_one_term_merge(self):
        # Exact reviewer reproduction: three separate explicit statements
        # about the same canonical term across a session.
        messages = [
            "I say fog of war, not blocked scope.",
            "Fog of war, aka fog.",
            "Fog of war means the unplanned part of a goal.",
        ]
        candidates = curation.find_candidates(messages)
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        candidate = matching[0]
        # The strongest explicit statement (a real definition) wins the
        # rendered meaning and kind, rather than the correction that
        # happened to be seen first.
        self.assertEqual(candidate.kind, "definition")
        self.assertEqual(candidate.meaning, "the unplanned part of a goal.")
        # Evidence from every kind survives the merge.
        self.assertEqual(candidate.not_terms, ("blocked scope",))
        self.assertEqual(candidate.aka_terms, ("fog",))

    def test_merge_is_order_independent(self):
        # The same three statements in a different order must still merge
        # to the identical result: deterministic, not first-match order.
        messages = [
            "Fog of war means the unplanned part of a goal.",
            "Fog of war, aka fog.",
            "I say fog of war, not blocked scope.",
        ]
        candidates = curation.find_candidates(messages)
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        candidate = matching[0]
        self.assertEqual(candidate.meaning, "the unplanned part of a goal.")
        self.assertEqual(candidate.not_terms, ("blocked scope",))
        self.assertEqual(candidate.aka_terms, ("fog",))

    def test_repeated_aliases_and_corrections_deduplicate_case_insensitively(self):
        messages = [
            "I say fog of war, not blocked scope.",
            "I say fog of war, not Blocked Scope.",
            "Fog of war, aka fog.",
            "Fog of war, aka Fog.",
        ]
        candidates = curation.find_candidates(messages)
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        # Only one unique anti-term and one unique alias survive, keeping
        # the first-seen casing.
        self.assertEqual(matching[0].not_terms, ("blocked scope",))
        self.assertEqual(matching[0].aka_terms, ("fog",))

    def test_two_corrections_for_one_term_accumulate_distinct_anti_terms(self):
        messages = [
            "I say fog of war, not blocked scope.",
            "I say fog of war, not open question.",
        ]
        candidates = curation.find_candidates(messages)
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].not_terms, ("blocked scope", "open question"))

    def test_correction_and_alias_without_definition_merge_meaning_from_correction(self):
        # No definition present: the correction (stronger than a bare
        # alias) supplies the meaning, and the alias still contributes its
        # aka term.
        messages = [
            "I say fog of war, not blocked scope.",
            "Fog of war, aka fog.",
        ]
        candidates = curation.find_candidates(messages)
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        candidate = matching[0]
        self.assertEqual(candidate.kind, "correction")
        self.assertEqual(candidate.not_terms, ("blocked scope",))
        self.assertEqual(candidate.aka_terms, ("fog",))

    def test_unrelated_terms_are_not_merged_together(self):
        messages = [
            "I say fog of war, not blocked scope.",
            "I say wayfinder, not roadmap.",
        ]
        candidates = curation.find_candidates(messages)
        terms = sorted(c.term.lower() for c in candidates)
        self.assertEqual(terms, ["fog of war", "wayfinder"])


class RepeatedTermRuleTest(unittest.TestCase):
    def test_repeated_term_below_threshold_is_ignored(self):
        messages = [
            "The scratchpad is where I keep temp files.",
            "Please clean up the scratchpad before committing.",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_repeated_term_at_threshold_with_supporting_sentence_is_captured(self):
        messages = [
            "The scratchpad is where I keep temp files.",
            "Please clean up the scratchpad before committing.",
            "I always dump drafts into the scratchpad first.",
        ]
        candidates = curation.find_candidates(messages)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.term, "scratchpad")
        self.assertEqual(candidate.kind, "repeated")
        self.assertEqual(candidate.frequency, 3)
        self.assertIn("temp files", candidate.meaning)

    def test_custom_min_repetitions_threshold_is_honored(self):
        messages = [
            "The scratchpad is where I keep temp files.",
            "Please clean up the scratchpad before committing.",
        ]
        candidates = curation.find_candidates(messages, min_repetitions=2)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].term, "scratchpad")

    def test_stopwords_never_qualify_regardless_of_frequency(self):
        messages = [
            "This is the thing I want to use.",
            "That is the thing I need to use again.",
            "Here is the thing I will use once more.",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_common_programming_keywords_never_qualify(self):
        messages = [
            "The function needs a fix in this file.",
            "That function also broke the build once.",
            "Another function bug appeared in the branch.",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_bigram_preferred_over_constituent_unigrams(self):
        messages = [
            "A trajectory audit is a full replay of an agent run to find drift.",
            "Every trajectory audit takes about an hour to run today.",
            "The last trajectory audit caught a real drift bug quickly.",
        ]
        candidates = curation.find_candidates(messages)
        terms = [c.term for c in candidates]
        self.assertIn("trajectory audit", terms)
        self.assertNotIn("trajectory", terms)
        self.assertNotIn("audit", terms)

    def test_ambiguity_rejection_drops_repeated_term_without_definitional_sentence(self):
        messages = [
            "Fix the widget please today.",
            "The widget is broken again this week.",
            "Can you check the widget once more tomorrow?",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_ambiguity_rejection_drops_term_with_too_short_inferred_meaning(self):
        # "is" connector present, but the remainder is under three words.
        messages = [
            "A gizmo is small.",
            "This gizmo is small.",
            "That gizmo is small too now.",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_explicit_correction_suppresses_duplicate_repeated_candidate(self):
        messages = [
            "I say fog of war, not blocked scope.",
            "The fog of war is real again this sprint.",
            "We hit fog of war on this ticket too.",
            "Fog of war struck again on the release.",
        ]
        candidates = curation.find_candidates(messages)
        # Only the explicit correction should surface, not a second
        # "repeated" duplicate for the same term.
        matching = [c for c in candidates if c.term.lower() == "fog of war"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].kind, "correction")


class PortabilityGateTest(unittest.TestCase):
    """Per the issue's non-goal, project-specific vocabulary belongs in a
    repo's own CONTEXT.md, never the personal glossary. The portability gate
    must deterministically reject a candidate whose term or meaning names
    itself as scoped to one specific codebase, even when it was stated as an
    explicit correction/alias/definition that would otherwise always
    qualify."""

    def test_reviewer_reproduction_project_specific_definition_is_rejected(self):
        # Exact reviewer reproduction: must not become writable.
        messages = [
            "Define payment widget as the checkout button unique to this "
            "repository."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_project_scoped_correction_is_rejected(self):
        messages = ["I say deploy gate, not the release check specific to our codebase."]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_project_scoped_alias_is_rejected(self):
        messages = [
            "The onboarding flow unique to this project, aka the setup wizard."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_project_scoped_term_text_itself_is_rejected(self):
        messages = [
            "Define the checkout button in this repository as the payment "
            "widget everyone clicks."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_portable_definition_still_qualifies(self):
        # Positive control: a genuinely portable definition, structurally
        # identical to the rejected case, must still be captured.
        messages = [
            "Define trajectory audit as a full replay of an agent run to "
            "find where it drifted."
        ]
        candidates = curation.find_candidates(messages)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].term, "trajectory audit")

    def test_portable_correction_still_qualifies(self):
        # Positive control for the correction rule specifically.
        candidates = curation.find_candidates(["I say wayfinder, not roadmap."])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].term, "wayfinder")

    def test_project_scoped_repeated_term_is_rejected(self):
        messages = [
            "The payment widget in this repository is the checkout button.",
            "Fix the payment widget in this repository before release.",
            "The payment widget in this repository broke again today.",
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_unique_to_this_workspace_is_rejected(self):
        messages = [
            "Define build cache as the artifact directory unique to this "
            "workspace."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_specific_to_named_org_is_rejected(self):
        messages = ["I say deploy gate, not the release check specific to Acme."]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_proprietary_to_named_org_is_rejected(self):
        messages = [
            "The onboarding flow proprietary to FooCorp, aka the setup wizard."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_only_used_in_this_codebase_is_rejected(self):
        messages = [
            "Define shim layer as the adapter only used in this codebase."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_only_defined_in_our_service_is_rejected(self):
        messages = ["I say retry budget, not the backoff limit only defined in our service."]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_only_exists_in_the_monorepo_is_rejected(self):
        messages = [
            "Define shared kernel as the module that only exists in the "
            "monorepo."
        ]
        self.assertEqual(curation.find_candidates(messages), [])

    def test_our_workspace_scope_is_rejected(self):
        # The base scope regex now also recognizes "workspace" as a scoped
        # noun alongside repo/project/codebase/etc.
        messages = ["I say lockfile, not the dependency snapshot in our workspace."]
        self.assertEqual(curation.find_candidates(messages), [])


class ApplyCandidatesTest(unittest.TestCase):
    def test_inserts_new_term_alphabetized_and_revalidates(self):
        candidates = [
            curation.Candidate(
                term="bravo", meaning="second term.", kind="repeated", evidence=""
            )
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(len(applied), 1)
        parsed = curation.parse_glossary(updated)
        self.assertEqual(
            [entry.term for entry in parsed.entries], ["alpha", "bravo", "charlie"]
        )

    def test_never_modifies_locked_term(self):
        candidates = [
            curation.Candidate(
                term="charlie",
                meaning="a hostile rewrite attempt.",
                kind="repeated",
                evidence="",
            )
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, POPULATED_GLOSSARY)

    def test_never_duplicates_existing_unlocked_term_case_insensitively(self):
        candidates = [
            curation.Candidate(
                term="ALPHA",
                meaning="a different meaning.",
                kind="repeated",
                evidence="",
            )
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, POPULATED_GLOSSARY)

    def test_merges_new_aka_and_not_terms_into_existing_unlocked_entry(self):
        candidates = [
            curation.Candidate(
                term="alpha",
                meaning="a different meaning.",
                kind="repeated",
                evidence="",
                not_terms=("first-thing",),
                aka_terms=("primary",),
            )
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].term, "alpha")
        parsed = curation.parse_glossary(updated)
        entry = parsed.by_term_lower()["alpha"]
        # A merely "repeated" candidate's meaning never overrides the
        # existing one - only new metadata merges in.
        self.assertEqual(entry.meaning, "first term.")
        self.assertEqual(entry.not_terms, ("first-thing",))
        self.assertEqual(entry.aka_terms, ("primary",))

    def test_merge_deduplicates_aka_and_not_terms_case_insensitively_preserving_order(self):
        glossary = (
            "---\n\n"
            "- **alpha** — first term. *(not: legacy-alpha; aka: A)*\n"
        )
        candidates = [
            curation.Candidate(
                term="alpha",
                meaning="a different meaning.",
                kind="correction",
                evidence="",
                not_terms=("LEGACY-ALPHA", "old-alpha"),
                aka_terms=("a", "primary"),
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(len(applied), 1)
        parsed = curation.parse_glossary(updated)
        entry = parsed.by_term_lower()["alpha"]
        self.assertEqual(entry.not_terms, ("legacy-alpha", "old-alpha"))
        self.assertEqual(entry.aka_terms, ("A", "primary"))

    def test_stronger_definition_updates_existing_entrys_meaning(self):
        glossary = "---\n\n- **alpha** — a placeholder meaning.\n"
        candidates = [
            curation.Candidate(
                term="alpha",
                meaning="the operator's real definition of alpha.",
                kind="definition",
                evidence="",
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].meaning, "the operator's real definition of alpha.")
        parsed = curation.parse_glossary(updated)
        entry = parsed.by_term_lower()["alpha"]
        self.assertEqual(entry.meaning, "the operator's real definition of alpha.")

    def test_correction_and_alias_candidates_never_override_existing_meaning(self):
        glossary = "---\n\n- **alpha** — the original meaning.\n"
        candidates = [
            curation.Candidate(
                term="alpha",
                meaning="the operator's canonical term for something else.",
                kind="correction",
                evidence="",
                not_terms=("something-else",),
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(len(applied), 1)
        parsed = curation.parse_glossary(updated)
        entry = parsed.by_term_lower()["alpha"]
        self.assertEqual(entry.meaning, "the original meaning.")
        self.assertEqual(entry.not_terms, ("something-else",))

    def test_refinement_that_changes_nothing_is_skipped_as_a_no_op(self):
        glossary = (
            "---\n\n"
            "- **alpha** — first term. *(not: beta; aka: A)*\n"
        )
        candidates = [
            curation.Candidate(
                term="alpha",
                meaning="a different meaning entirely.",
                kind="correction",
                evidence="",
                not_terms=("beta",),
                aka_terms=("a",),
            )
        ]
        updated, applied = curation.apply_candidates(glossary, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, glossary)

    def test_refinement_never_touches_a_locked_entry(self):
        candidates = [
            curation.Candidate(
                term="charlie",
                meaning="the definitive real meaning.",
                kind="definition",
                evidence="",
                not_terms=("delta",),
                aka_terms=("gamma",),
            )
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(applied, [])
        self.assertEqual(updated, POPULATED_GLOSSARY)

    def test_never_deletes_any_existing_entry(self):
        candidates = [
            curation.Candidate(
                term="delta", meaning="fourth term.", kind="repeated", evidence=""
            )
        ]
        updated, _ = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        parsed = curation.parse_glossary(updated)
        terms = {entry.term for entry in parsed.entries}
        self.assertIn("alpha", terms)
        self.assertIn("charlie", terms)

    def test_inserting_first_entry_into_template_adds_separator_blank_line(self):
        candidates = [
            curation.Candidate(
                term="fog of war", meaning="the unplanned part.", kind="correction", evidence=""
            )
        ]
        updated, applied = curation.apply_candidates(TEMPLATE_TEXT, candidates)
        self.assertEqual(len(applied), 1)
        self.assertIn("---\n\n- **fog of war**", updated)
        curation.validate_glossary(updated)

    def test_applying_no_candidates_returns_unchanged_text(self):
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, [])
        self.assertEqual(applied, [])
        self.assertEqual(updated, POPULATED_GLOSSARY)

    def test_multiple_candidates_all_applied_and_still_alphabetized(self):
        candidates = [
            curation.Candidate(term="zulu", meaning="last.", kind="repeated", evidence=""),
            curation.Candidate(term="bravo", meaning="second.", kind="repeated", evidence=""),
        ]
        updated, applied = curation.apply_candidates(POPULATED_GLOSSARY, candidates)
        self.assertEqual(len(applied), 2)
        parsed = curation.parse_glossary(updated)
        self.assertEqual(
            [entry.term for entry in parsed.entries],
            ["alpha", "bravo", "charlie", "zulu"],
        )


if __name__ == "__main__":
    unittest.main()
