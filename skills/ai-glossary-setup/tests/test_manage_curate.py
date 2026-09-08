#!/usr/bin/env python3
"""Integration tests for automatic curation wired into manage.py: the shared
``curate`` action, its advisory locking under concurrency, and idempotent
install/removal of the Claude Code SessionEnd hook and the Opencode plugin.
"""

import importlib.util
import json
import shutil
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

NODE = shutil.which("node")
PLUGIN_RUNNER = Path(__file__).resolve().parent / "fixtures" / "run_opencode_plugin.mjs"


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
        self.claude_settings = self.root / "claude" / "settings.json"
        self.opencode_plugin_dir = self.root / "opencode" / "plugin"

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
            "--claude-settings-file",
            str(self.claude_settings),
            "--opencode-plugin-dir",
            str(self.opencode_plugin_dir),
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


class ClaudeHookLifecycleTest(ManageCuratePaths):
    def test_setup_installs_session_end_hook_pointing_at_curate(self):
        result = self.run_tool("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(self.claude_settings.read_text(encoding="utf-8"))
        session_end = settings["hooks"]["SessionEnd"]
        handlers = [hook for group in session_end for hook in group["hooks"]]
        managed = [h for h in handlers if h.get("_managed_by") == manage.CLAUDE_HOOK_MARKER]
        self.assertEqual(len(managed), 1)
        self.assertIn("curate", managed[0]["command"])
        self.assertIn(str(self.data_home), managed[0]["command"])

    def test_setup_preserves_unrelated_hooks_and_settings_keys(self):
        self.claude_settings.parent.mkdir(parents=True)
        self.claude_settings.write_text(
            json.dumps(
                {
                    "model": "claude-opus-4-6",
                    "hooks": {
                        "PostToolUse": [
                            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(self.claude_settings.read_text(encoding="utf-8"))
        self.assertEqual(settings["model"], "claude-opus-4-6")
        self.assertEqual(
            settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "echo hi"
        )
        self.assertIn("SessionEnd", settings["hooks"])

    def test_setup_is_idempotent_for_the_hook(self):
        self.run_tool("setup")
        first = self.claude_settings.read_text(encoding="utf-8")

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        second = self.claude_settings.read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_uninstall_removes_only_the_managed_hook(self):
        self.claude_settings.parent.mkdir(parents=True)
        self.claude_settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self.run_tool("setup")

        result = self.run_tool("uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(self.claude_settings.read_text(encoding="utf-8"))
        self.assertNotIn("SessionEnd", settings.get("hooks", {}))
        self.assertEqual(
            settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "echo hi"
        )

    def test_uninstall_tolerates_missing_settings_file(self):
        result = self.run_tool("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.claude_settings.exists())


class OpencodePluginLifecycleTest(ManageCuratePaths):
    def test_setup_installs_managed_plugin_file(self):
        result = self.run_tool("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        plugin_file = self.opencode_plugin_dir / manage.OPENCODE_PLUGIN_NAME
        self.assertTrue(plugin_file.exists())
        source = plugin_file.read_text(encoding="utf-8")
        self.assertIn(manage.OPENCODE_PLUGIN_MARKER, source)
        self.assertIn("session.idle", source)
        self.assertIn(str(self.data_home), source)

    def test_setup_preserves_unrelated_plugin_files(self):
        self.opencode_plugin_dir.mkdir(parents=True)
        other_plugin = self.opencode_plugin_dir / "other-plugin.js"
        other_plugin.write_text("// unrelated\n", encoding="utf-8")

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(other_plugin.read_text(encoding="utf-8"), "// unrelated\n")

    def test_setup_is_idempotent_for_the_plugin_file(self):
        self.run_tool("setup")
        plugin_file = self.opencode_plugin_dir / manage.OPENCODE_PLUGIN_NAME
        first = plugin_file.read_bytes()

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plugin_file.read_bytes(), first)

    def test_uninstall_removes_only_the_managed_plugin_file(self):
        self.opencode_plugin_dir.mkdir(parents=True)
        other_plugin = self.opencode_plugin_dir / "other-plugin.js"
        other_plugin.write_text("// unrelated\n", encoding="utf-8")
        self.run_tool("setup")

        result = self.run_tool("uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        plugin_file = self.opencode_plugin_dir / manage.OPENCODE_PLUGIN_NAME
        self.assertFalse(plugin_file.exists())
        self.assertTrue(other_plugin.exists())

    def test_uninstall_tolerates_missing_plugin_directory(self):
        result = self.run_tool("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.opencode_plugin_dir.exists())

    def test_uninstall_leaves_foreign_file_with_our_reserved_name_untouched(self):
        self.opencode_plugin_dir.mkdir(parents=True)
        plugin_file = self.opencode_plugin_dir / manage.OPENCODE_PLUGIN_NAME
        plugin_file.write_text("// not ours\n", encoding="utf-8")

        result = self.run_tool("uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plugin_file.read_text(encoding="utf-8"), "// not ours\n")


@unittest.skipUnless(NODE, "node is required to exercise the generated Opencode plugin")
class OpencodePluginAdapterReportingTest(ManageCuratePaths):
    """Adapter-level tests for the generated Opencode plugin file itself,
    per the issue's testing decision that harness adapters are tested for
    correct command invocation and lifecycle behavior. These load the real
    generated plugin as an ES module and drive its ``session.idle`` handler
    against a mocked ``client`` — but the handler's own subprocess spawn
    still runs the real ``curate`` command unmodified, so stdout/stderr
    capture and exit-code handling are exercised end to end rather than
    mocked away.
    """

    def setUp(self):
        super().setUp()
        self.opencode_plugin_dir.mkdir(parents=True)
        source = manage._opencode_plugin_source(
            self.data_home, self.claude, self.agents
        )
        self.plugin_file = self.opencode_plugin_dir / manage.OPENCODE_PLUGIN_NAME
        self.plugin_file.write_text(source, encoding="utf-8")

    def run_plugin(self, messages: list[dict]) -> dict:
        result = subprocess.run(
            [NODE, str(PLUGIN_RUNNER), str(self.plugin_file), json.dumps(messages)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    @staticmethod
    def _user_message(text: str) -> dict:
        return {"info": {"role": "user"}, "parts": [{"type": "text", "text": text}]}

    def test_generated_plugin_has_valid_syntax(self):
        result = subprocess.run(
            [NODE, "--check", str(self.plugin_file)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_applied_change_is_reported_through_a_toast(self):
        outcome = self.run_plugin(
            [self._user_message("I say fog of war, not blocked scope.")]
        )
        self.assertIsNone(outcome["error"])
        self.assertEqual(len(outcome["toastCalls"]), 1)
        toast = outcome["toastCalls"][0]["body"]
        self.assertEqual(toast["variant"], "info")
        self.assertIn("fog of war", toast["message"])
        glossary = (self.data_home / "glossary.md").read_text(encoding="utf-8")
        self.assertIn("fog of war", glossary)

    def test_no_qualifying_candidates_still_reports_a_toast(self):
        outcome = self.run_plugin(
            [self._user_message("Just a normal unremarkable message.")]
        )
        self.assertIsNone(outcome["error"])
        self.assertEqual(len(outcome["toastCalls"]), 1)
        toast = outcome["toastCalls"][0]["body"]
        self.assertEqual(toast["variant"], "info")
        self.assertIn("no qualifying", toast["message"])

    def test_curate_command_failure_is_surfaced_as_an_error_toast(self):
        # Force the shared curate command to exit nonzero: replace the
        # claude-file target (a file the command must write through) with a
        # directory, so the write fails during synchronization.
        self.claude.parent.mkdir(parents=True, exist_ok=True)
        self.claude.mkdir()

        outcome = self.run_plugin(
            [self._user_message("I say fog of war, not blocked scope.")]
        )

        self.assertIsNone(outcome["error"])
        self.assertEqual(len(outcome["toastCalls"]), 1)
        toast = outcome["toastCalls"][0]["body"]
        self.assertEqual(toast["variant"], "error")
        self.assertTrue(toast["message"])

    def test_failure_toast_never_reports_success_language(self):
        self.claude.parent.mkdir(parents=True, exist_ok=True)
        self.claude.mkdir()

        outcome = self.run_plugin(
            [self._user_message("I say fog of war, not blocked scope.")]
        )

        toast = outcome["toastCalls"][0]["body"]
        self.assertNotIn("added", toast["message"])
        self.assertNotIn("no qualifying", toast["message"])


if __name__ == "__main__":
    unittest.main()
