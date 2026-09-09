#!/usr/bin/env python3
"""Integration tests for automatic curation wired into manage.py: the shared
``curate`` action, its advisory locking under concurrency, and cleanup of
leftover Claude Code SessionEnd hooks and Opencode plugins from prior installs.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "manage.py"
SPEC = importlib.util.spec_from_file_location("ai_glossary_manage_curate", SCRIPT)
manage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(manage)


def claude_transcript(*messages: str) -> str:
    lines = []
    for message in messages:
        lines.append(
            json.dumps({"type": "user", "message": {"role": "user", "content": message}})
        )
    return "\n".join(lines)


class ManageCuratePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_home = self.root / "config" / "ai-glossary"
        self.claude = self.root / "claude" / "CLAUDE.md"
        self.agents = self.root / "codex" / "AGENTS.md"

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, action: str, *extra_args: str, input_text: str = None):
        args = [
            sys.executable,
            str(SCRIPT),
            action,
            "--data-home",
            str(self.data_home),
            "--claude-file",
            str(self.claude),
            "--agents-file",
            str(self.agents),
            *extra_args,
        ]
        return subprocess.run(
            args, input=input_text, check=False, capture_output=True, text=True
        )


class CurateActionTest(ManageCuratePaths):
    def test_curate_creates_glossary_on_first_run_and_adds_qualifying_terms(self):
        transcript = claude_transcript(
            "I say fog of war, not blocked scope.",
        )
        result = self.run_tool(
            "curate", "--source", "claude", input_text=transcript
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fog of war", result.stdout)
        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("- **fog of war**", glossary)

    def test_curate_synchronizes_managed_copies_after_a_qualifying_write(self):
        transcript = claude_transcript("I say fog of war, not blocked scope.")
        self.run_tool("curate", "--source", "claude", input_text=transcript)
        claude_text = self.claude.read_text(encoding="utf-8")
        agents_text = self.agents.read_text(encoding="utf-8")
        self.assertIn("fog of war", claude_text)
        self.assertIn("fog of war", agents_text)

    def test_curate_with_no_qualifying_candidates_leaves_glossary_untouched(self):
        # First establish a glossary.
        self.run_tool("setup")
        before = (self.data_home / "glossary.md").read_text(encoding="utf-8")

        transcript = claude_transcript("Just a normal unremarkable message.")
        result = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no qualifying", result.stdout)
        after = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_curate_never_adds_duplicate_on_repeated_invocation(self):
        transcript = claude_transcript("I say fog of war, not blocked scope.")
        self.run_tool("curate", "--source", "claude", input_text=transcript)
        first = (self.data_home / "glossary.md").read_text(encoding="utf-8")

        second = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("no qualifying", second.stdout)
        after = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertEqual(first, after)

    def test_curate_respects_existing_locked_term(self):
        self.data_home.mkdir(parents=True)
        (self.data_home / "glossary.md").write_text(
            "# Mine\n\n---\n\n- **fog of war** — the operator's own locked wording. *(locked)*\n",
            encoding="utf-8",
        )
        transcript = claude_transcript(
            "I say fog of war, not blocked scope.",
        )
        result = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no qualifying", result.stdout)
        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("the operator's own locked wording", glossary)

    def test_curate_reads_claude_session_end_envelope_transcript_path(self):
        transcript_file = self.root / "transcript.jsonl"
        transcript_file.write_text(
            claude_transcript("I say wayfinder, not roadmap."), encoding="utf-8"
        )
        envelope = json.dumps(
            {
                "session_id": "abc",
                "transcript_path": str(transcript_file),
                "cwd": str(self.root),
                "hook_event_name": "SessionEnd",
                "reason": "other",
            }
        )
        result = self.run_tool("curate", "--source", "claude", input_text=envelope)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wayfinder", result.stdout)
        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("wayfinder", glossary)

    def test_curate_reads_opencode_message_payload_from_stdin(self):
        payload = json.dumps(
            {
                "messages": [
                    {
                        "info": {"role": "user"},
                        "parts": [
                            {"type": "text", "text": "I say wayfinder, not roadmap."}
                        ],
                    }
                ]
            }
        )
        result = self.run_tool("curate", "--source", "opencode", input_text=payload)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("wayfinder", result.stdout)

    def test_curate_resynchronizes_stale_managed_copy_with_no_new_candidates(self):
        # Simulate a prior invocation that wrote the canonical glossary but
        # then failed to synchronize one managed copy (a crash, a full disk,
        # a permission error partway through) — the classic partial-failure
        # scenario. The next invocation, even finding no new candidates,
        # must still bring the stale copy back in line with the canonical
        # file rather than treating "nothing new to add" as "nothing to do".
        self.run_tool("setup")
        canonical = self.data_home / "glossary.md"
        canonical.write_text(
            canonical.read_text(encoding="utf-8").rstrip("\n")
            + "\n- **fog of war** — the unplanned part of a goal.\n",
            encoding="utf-8",
        )
        # Both managed copies still reflect the pre-append canonical content
        # - as if a previous invocation wrote the canonical file directly
        # but crashed before synchronizing either copy.
        stale_agents_text = self.agents.read_text(encoding="utf-8")

        transcript = claude_transcript("Just a normal unremarkable message.")
        result = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no qualifying", result.stdout)
        agents_text = self.agents.read_text(encoding="utf-8")
        self.assertNotEqual(agents_text, stale_agents_text)
        self.assertIn("fog of war", agents_text)
        claude_text = self.claude.read_text(encoding="utf-8")
        self.assertIn("fog of war", claude_text)

    def test_curate_continues_to_second_target_when_first_sync_target_fails(self):
        transcript = claude_transcript("I say fog of war, not blocked scope.")
        # Make the claude-file target unwritable as a directory so
        # synchronizing it fails, while the agents-file target is healthy.
        self.claude.parent.mkdir(parents=True, exist_ok=True)
        self.claude.mkdir()

        result = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertNotEqual(result.returncode, 0)
        agents_text = self.agents.read_text(encoding="utf-8")
        self.assertIn("fog of war", agents_text)
        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("fog of war", glossary)

    def test_curate_only_considers_operator_messages_from_transcript(self):
        transcript = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "role": "assistant",
                            "content": "I say fog of war, not blocked scope.",
                        },
                    }
                ),
            ]
        )
        result = self.run_tool("curate", "--source", "claude", input_text=transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no qualifying", result.stdout)


class CurateConcurrencyTest(ManageCuratePaths):
    def test_concurrent_curate_invocations_do_not_lose_either_update(self):
        transcript_a = claude_transcript(
            "The wayfinder is my term for planning a foggy goal step by step.",
            "I keep using the wayfinder pattern for big migrations.",
            "The wayfinder helped a lot this week.",
        )
        transcript_b = claude_transcript(
            "A trajectory audit is a full replay of an agent run to find drift.",
            "Let's do a trajectory audit before shipping today.",
            "Another trajectory audit caught the bug quickly.",
        )

        results = {}

        def _run(key, transcript):
            results[key] = self.run_tool(
                "curate", "--source", "claude", input_text=transcript
            )

        thread_a = threading.Thread(target=_run, args=("a", transcript_a))
        thread_b = threading.Thread(target=_run, args=("b", transcript_b))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        self.assertEqual(results["a"].returncode, 0, results["a"].stderr)
        self.assertEqual(results["b"].returncode, 0, results["b"].stderr)

        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("wayfinder", glossary)
        self.assertIn("trajectory audit", glossary)
        # Confirm the resulting glossary is still well-formed after the
        # interleaved concurrent writes.
        sys.path.insert(0, str(SKILL_DIR))
        import curation

        curation.validate_glossary(glossary)


if __name__ == "__main__":
    unittest.main()
