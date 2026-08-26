#!/usr/bin/env python3

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "manage.py"
SPEC = importlib.util.spec_from_file_location("ai_glossary_manage", SCRIPT)
manage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(manage)


class ManageGlossaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_home = self.root / "config" / "ai-glossary"
        self.claude = self.root / "claude" / "CLAUDE.md"
        self.agents = self.root / "codex" / "AGENTS.md"

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, action: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                action,
                "--data-home",
                str(self.data_home),
                "--claude-file",
                str(self.claude),
                "--agents-file",
                str(self.agents),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def assert_one_complete_block(self, path: Path, glossary: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(manage.START), 1)
        self.assertEqual(text.count(manage.END), 1)
        self.assertIn(manage.managed_block(glossary), text)

    def test_fresh_setup_creates_data_and_both_global_files(self):
        result = self.run_tool("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        glossary = self.data_home.joinpath("glossary.md").read_text(encoding="utf-8")
        self.assertEqual(glossary, SKILL_DIR.joinpath("templates/glossary.md").read_text(encoding="utf-8"))
        self.assert_one_complete_block(self.claude, glossary)
        self.assert_one_complete_block(self.agents, glossary)

    def test_setup_migrates_legacy_import_and_preserves_unrelated_content(self):
        self.data_home.mkdir(parents=True)
        glossary = "# Mine\n\n- **term** — meaning.\n"
        self.data_home.joinpath("glossary.md").write_text(glossary, encoding="utf-8")
        self.claude.parent.mkdir(parents=True)
        self.claude.write_text(
            "before\n@/old/.config/ai-glossary/glossary.md\nafter\n", encoding="utf-8"
        )
        self.agents.parent.mkdir(parents=True)
        self.agents.write_text("agent instructions\n", encoding="utf-8")

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("@/old/.config/ai-glossary/glossary.md", self.claude.read_text())
        self.assertIn("before\nafter\n", self.claude.read_text())
        self.assertIn("agent instructions\n", self.agents.read_text())
        self.assert_one_complete_block(self.claude, glossary)
        self.assert_one_complete_block(self.agents, glossary)

    def test_repair_replaces_old_blocks_with_changed_complete_glossary(self):
        self.assertEqual(self.run_tool("setup").returncode, 0)
        changed = "# Changed glossary\n\n- **new term** — new meaning."
        self.data_home.joinpath("glossary.md").write_text(changed, encoding="utf-8")
        with self.claude.open("a", encoding="utf-8") as handle:
            handle.write(manage.managed_block("duplicate stale glossary\n"))

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        for target in (self.claude, self.agents):
            self.assert_one_complete_block(target, changed)
            self.assertNotIn("# Personal Glossary", target.read_text())

    def test_setup_is_byte_for_byte_idempotent(self):
        self.assertEqual(self.run_tool("setup").returncode, 0)
        first = (self.claude.read_bytes(), self.agents.read_bytes())

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.claude.read_bytes(), self.agents.read_bytes()), first)
        self.assertEqual(result.stdout.strip(), "setup already complete")

    def test_uninstall_removes_only_blocks_and_legacy_lines_and_retains_data(self):
        self.data_home.mkdir(parents=True)
        glossary_path = self.data_home / "glossary.md"
        glossary_path.write_text("canonical vocabulary\n", encoding="utf-8")
        for target, unrelated in (
            (self.claude, "claude unrelated\n"),
            (self.agents, "agents unrelated\n"),
        ):
            target.parent.mkdir(parents=True)
            target.write_text(
                unrelated
                + "@/legacy/ai-glossary/glossary.md\n"
                + manage.managed_block("stale glossary\n"),
                encoding="utf-8",
            )

        result = self.run_tool("uninstall")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.claude.read_text(), "claude unrelated\n")
        self.assertEqual(self.agents.read_text(), "agents unrelated\n")
        self.assertEqual(glossary_path.read_text(), "canonical vocabulary\n")
        self.assertIn(f"glossary retained at {glossary_path.resolve()}", result.stdout)

    def test_uninstall_tolerates_missing_targets(self):
        result = self.run_tool("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.agents.exists())
        self.assertFalse(self.data_home.exists())

    def test_partial_managed_block_fails_without_rewriting_target(self):
        self.data_home.mkdir(parents=True)
        self.data_home.joinpath("glossary.md").write_text("glossary\n", encoding="utf-8")
        self.claude.parent.mkdir(parents=True)
        original = "unrelated\n" + manage.START + "\nincomplete\n"
        self.claude.write_text(original, encoding="utf-8")

        result = self.run_tool("setup")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.claude.read_text(), original)
        self.assertIn("without a matching end marker", result.stderr)


if __name__ == "__main__":
    unittest.main()
