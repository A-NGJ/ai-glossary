#!/usr/bin/env python3

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def expected_guidance(self) -> str:
        return manage.synchronization_guidance(
            self.data_home.resolve(), self.claude.resolve(), self.agents.resolve()
        )

    def assert_one_complete_block(self, path: Path, glossary: str) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count(manage.START), 1)
        self.assertEqual(text.count(manage.END), 1)
        self.assertIn(
            manage.managed_block(glossary, self.expected_guidance()), text
        )

    def test_fresh_setup_creates_data_and_both_global_files(self):
        result = self.run_tool("setup")
        self.assertEqual(result.returncode, 0, result.stderr)
        glossary = self.data_home.joinpath("glossary.md").read_text(encoding="utf-8")
        self.assertEqual(glossary, SKILL_DIR.joinpath("templates/glossary.md").read_text(encoding="utf-8"))
        self.assert_one_complete_block(self.claude, glossary)
        self.assert_one_complete_block(self.agents, glossary)
        for target in (self.claude, self.agents):
            block = target.read_text(encoding="utf-8")
            self.assertIn(
                "`$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to "
                "`~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or empty",
                block,
            )
            self.assertIn("generated copies; never edit either block directly", block)
            self.assertIn("After every canonical edit, immediately synchronize", block)
            self.assertIn(f"--data-home {self.data_home.resolve()}", block)
            self.assertIn(f"--claude-file {self.claude.resolve()}", block)
            self.assertIn(f"--agents-file {self.agents.resolve()}", block)

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

    def test_setup_repair_and_uninstall_preserve_mixed_line_endings(self):
        self.data_home.mkdir(parents=True)
        glossary_path = self.data_home / "glossary.md"
        glossary_path.write_text("# First\n", encoding="utf-8")
        self.claude.parent.mkdir(parents=True)
        unrelated = b"alpha\r\nbeta\ntail\r\n"
        self.claude.write_bytes(
            b"alpha\r\n"
            b"@C:\\config\\ai-glossary\\glossary.md\r\n"
            b"beta\n"
            + manage.managed_block("# Stale\r\n").encode()
            + b"tail\r\n"
        )

        setup = self.run_tool("setup")

        self.assertEqual(setup.returncode, 0, setup.stderr)
        self.assertEqual(
            self.claude.read_bytes(),
            unrelated
            + manage.managed_block("# First\n", self.expected_guidance()).encode(),
        )

        glossary_path.write_text("# Repaired\n", encoding="utf-8")
        repair = self.run_tool("setup")

        self.assertEqual(repair.returncode, 0, repair.stderr)
        self.assertEqual(
            self.claude.read_bytes(),
            unrelated
            + manage.managed_block("# Repaired\n", self.expected_guidance()).encode(),
        )

        uninstall = self.run_tool("uninstall")

        self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
        self.assertEqual(self.claude.read_bytes(), unrelated)

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

    def test_default_paths_honor_xdg_and_harness_environment(self):
        with mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "xdg"),
                "CLAUDE_CONFIG_DIR": str(self.root / "custom-claude"),
                "CODEX_HOME": str(self.root / "custom-codex"),
            },
            clear=True,
        ):
            self.assertEqual(
                manage.default_data_home(), self.root / "xdg" / "ai-glossary"
            )
            self.assertEqual(
                manage.default_claude_file(), self.root / "custom-claude" / "CLAUDE.md"
            )
            self.assertEqual(
                manage.default_agents_file(), self.root / "custom-codex" / "AGENTS.md"
            )

    def test_empty_xdg_and_harness_environment_use_home_fallbacks(self):
        with mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": "",
                "CLAUDE_CONFIG_DIR": "",
                "CODEX_HOME": "",
            },
            clear=True,
        ):
            home = self.root / "home"
            self.assertEqual(
                manage.default_data_home(), home / ".config" / "ai-glossary"
            )
            self.assertEqual(
                manage.default_claude_file(), home / ".claude" / "CLAUDE.md"
            )
            self.assertEqual(
                manage.default_agents_file(), home / ".codex" / "AGENTS.md"
            )

    def test_explicit_data_home_curation_pair_edits_and_syncs_same_glossary(self):
        default_glossary = self.root / "xdg" / "ai-glossary" / "glossary.md"
        default_glossary.parent.mkdir(parents=True)
        default_glossary.write_text("# Wrong default\n", encoding="utf-8")

        setup = self.run_tool("setup")
        self.assertEqual(setup.returncode, 0, setup.stderr)
        block = self.claude.read_text(encoding="utf-8")
        match = re.search(r"<!-- ai-glossary:curation (\{.*\}) -->", block)
        self.assertIsNotNone(match)
        pair = json.loads(match.group(1))
        canonical = Path(pair["canonical_glossary"])
        command = shlex.split(pair["sync_command"])

        self.assertEqual(canonical, self.data_home.resolve() / "glossary.md")
        self.assertEqual(
            Path(command[command.index("--data-home") + 1]), self.data_home.resolve()
        )
        approved = "# Explicit override\n\n- **paired term** — approved meaning.\n"
        canonical.write_text(approved, encoding="utf-8")
        sync = subprocess.run(command, check=False, capture_output=True, text=True)

        self.assertEqual(sync.returncode, 0, sync.stderr)
        self.assertEqual(default_glossary.read_text(encoding="utf-8"), "# Wrong default\n")
        for target in (self.claude, self.agents):
            generated = target.read_text(encoding="utf-8")
            self.assertIn(approved, generated)
            self.assertNotIn("# Wrong default", generated)

    def test_curation_skill_resolves_managed_pair_before_environment_fallback(self):
        skill = SKILL_DIR.parent.joinpath("curate-glossary/SKILL.md").read_text(
            encoding="utf-8"
        )
        managed = skill.index("Before reading a glossary, inspect the current global")
        fallback = skill.index("When no current managed block supplies the pair")
        read = skill.index("Read only the canonical glossary from the resolved pair")
        validate_existing = skill.index("Validate the existing term grammar")
        candidates = skill.index("## Build the candidate set")
        validate_update = skill.index("Validate the complete proposed content")
        write = skill.index("Once valid, write the canonical file")
        apply = skill.index("Run the synchronization command from the same resolved pair")

        self.assertLess(managed, fallback)
        self.assertLess(fallback, read)
        self.assertLess(read, validate_existing)
        self.assertLess(validate_existing, candidates)
        self.assertLess(candidates, validate_update)
        self.assertLess(validate_update, write)
        self.assertLess(write, apply)
        self.assertIn("require the pairs to match", skill)
        self.assertIn("For an older block without that\ncomment", skill)
        self.assertIn("Never\ncombine a canonical path from one source", skill)
        self.assertIn("Report and stop if\nsynchronization fails", skill)
        self.assertIn("never edit a managed block directly", skill)

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
