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
TEMPLATE = SKILL_DIR / "templates" / "glossary.md"
SPEC = importlib.util.spec_from_file_location("ai_glossary_manage", SCRIPT)
manage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(manage)

# A stale tool-owned header from before curation guidance moved out of the
# embedded header and into the curate-glossary skill.
STALE_HEADER = (
    "# Personal Glossary\n"
    "\n"
    "Operator meta-language — these terms are how the operator names things; use\n"
    "them. Inside a repo, its CONTEXT.md wins on conflict.\n"
    "\n"
    "Use terms naturally — never announce or narrate that you are applying the\n"
    "glossary. When the operator uses an anti-term, gently point to the canonical\n"
    "term; don't just avoid the anti-term in your own reply.\n"
    "\n"
    "Curation: capture only portable language whose meaning survives moving to\n"
    "another repo — project terms belong in that repo's CONTEXT.md. Mention every\n"
    "change in passing. Ask before deleting an entry.\n"
    "\n"
    "Entry grammar — one line per term, flat and alphabetized:\n"
    "`- **term** — one-line meaning. *(not: anti-term, …; aka: alias, …)*`\n"
    "\n"
    "---\n"
)

OPERATOR_ENTRIES = (
    "- **alpha** — first meaning. *(not: beta; aka: a)*\n"
    "- **beta** — second meaning. *(not: gamma; aka: b)*\n"
    "- **delta** — delta meaning.\n"
)


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

    def template_text(self) -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    def write_glossary(self, content: str) -> Path:
        self.data_home.mkdir(parents=True, exist_ok=True)
        path = self.data_home / "glossary.md"
        path.write_bytes(content.encode("utf-8"))
        return path

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

    def test_setup_migrates_stale_header_and_preserves_entries_and_aliases(self):
        glossary_path = self.write_glossary(STALE_HEADER + OPERATOR_ENTRIES)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.template_text() + OPERATOR_ENTRIES
        migrated = glossary_path.read_text(encoding="utf-8")
        self.assertEqual(migrated, expected)
        self.assertIn(
            f"migrated {glossary_path.resolve()} header to current template",
            result.stdout,
        )
        # The obsolete curation guidance is gone from the migrated header.
        self.assertNotIn("Curation: capture only portable language", migrated)
        self.assertNotIn("Entry grammar — one line per term", migrated)
        self.assert_one_complete_block(self.claude, expected)
        self.assert_one_complete_block(self.agents, expected)
        # Every term, anti-term, and alias survives byte-for-byte.
        self.assertTrue(migrated.endswith(OPERATOR_ENTRIES))
        self.assertIn(OPERATOR_ENTRIES, self.claude.read_text(encoding="utf-8"))
        self.assertIn(OPERATOR_ENTRIES, self.agents.read_text(encoding="utf-8"))

    def test_setup_migration_is_byte_for_byte_idempotent(self):
        glossary_path = self.write_glossary(STALE_HEADER + OPERATOR_ENTRIES)
        self.assertEqual(self.run_tool("setup").returncode, 0)
        migrated = glossary_path.read_bytes()

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(glossary_path.read_bytes(), migrated)
        self.assertEqual(result.stdout.strip(), "setup already complete")

    def test_setup_leaves_current_header_byte_identical(self):
        current = self.template_text() + OPERATOR_ENTRIES
        glossary_path = self.write_glossary(current)

        first = self.run_tool("setup")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotIn("migrated", first.stdout)
        self.assertEqual(glossary_path.read_bytes(), current.encode("utf-8"))
        self.assert_one_complete_block(self.claude, current)
        self.assert_one_complete_block(self.agents, current)

        second = self.run_tool("setup")

        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), "setup already complete")
        self.assertEqual(glossary_path.read_bytes(), current.encode("utf-8"))

    def test_setup_leaves_glossary_without_separator_untouched(self):
        fixture = "# Mine\n\n- **term** — meaning.\n"
        glossary_path = self.write_glossary(fixture)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("migrated", result.stdout)
        self.assertEqual(glossary_path.read_text(encoding="utf-8"), fixture)
        self.assert_one_complete_block(self.claude, fixture)
        self.assert_one_complete_block(self.agents, fixture)

    def test_setup_migration_preserves_crlf_line_endings(self):
        entries = "- **term** — meaning.\r\n"
        stale = "# Personal Glossary\r\n\r\nOld header.\r\n\r\n---\r\n" + entries
        glossary_path = self.write_glossary(stale)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.template_text().replace("\n", "\r\n") + entries
        expected_bytes = expected.encode("utf-8")
        self.assertEqual(glossary_path.read_bytes(), expected_bytes)
        self.assertEqual(
            expected_bytes.count(b"\n"), expected_bytes.count(b"\r\n")
        )

        again = self.run_tool("setup")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout.strip(), "setup already complete")
        self.assertEqual(glossary_path.read_bytes(), expected.encode("utf-8"))

    def test_setup_migration_preserves_cr_only_line_endings(self):
        entries = "- **term** — meaning.\r"
        stale = "# Personal Glossary\r\rOld header.\r\r---\r" + entries
        glossary_path = self.write_glossary(stale)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.template_text().replace("\n", "\r") + entries
        expected_bytes = expected.encode("utf-8")
        self.assertEqual(glossary_path.read_bytes(), expected_bytes)
        # A classic-Mac CR-only file stays CR-only: the migrated header must
        # reuse the body's lone-CR endings instead of splicing in LF.
        self.assertNotIn(b"\n", expected_bytes)

        again = self.run_tool("setup")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout.strip(), "setup already complete")
        self.assertEqual(glossary_path.read_bytes(), expected_bytes)

    def test_managed_block_reuses_each_glossary_line_ending(self):
        guidance = "curation guidance\n"
        cases = {
            "lf-terminated": ("# Glossary\n", "# Glossary\n"),
            "crlf-terminated": ("# Glossary\r\n", "# Glossary\r\n"),
            "cr-terminated": ("# Glossary\r", "# Glossary\r"),
            "unterminated-no-newline": ("# Glossary", "# Glossary\n"),
            "lf-unterminated": ("# One\nTwo", "# One\nTwo\n"),
            "crlf-unterminated": ("# One\r\nTwo", "# One\r\nTwo\r\n"),
            "cr-unterminated": ("# One\rTwo", "# One\rTwo\r"),
        }
        for name, (glossary, content) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    manage.managed_block(glossary, guidance),
                    f"{manage.START}\n{guidance}{content}{manage.END}\n",
                )

    def test_setup_cr_only_glossary_block_has_no_foreign_lf_tail(self):
        glossary = "# Mine\r\r- **term** — meaning.\r"
        glossary_path = self.write_glossary(glossary)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(glossary_path.read_bytes(), glossary.encode("utf-8"))
        expected_block = manage.managed_block(glossary, self.expected_guidance())
        for target in (self.claude, self.agents):
            generated = target.read_bytes()
            self.assertEqual(generated, expected_block.encode("utf-8"))
            # The embedded glossary keeps its lone-CR ending; the generator
            # must not splice an LF or CRLF before the end marker.
            self.assertIn(
                ("meaning.\r" + manage.END + "\n").encode("utf-8"), generated
            )
            self.assertNotIn(b"\r\n", generated)

        again = self.run_tool("setup")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(again.stdout.strip(), "setup already complete")
        for target in (self.claude, self.agents):
            self.assertEqual(target.read_bytes(), expected_block.encode("utf-8"))

    def test_setup_migrates_symlinked_glossary_through_its_target(self):
        target = self.root / "dotfiles" / "glossary.md"
        target.parent.mkdir(parents=True)
        target.write_text(STALE_HEADER + OPERATOR_ENTRIES, encoding="utf-8")
        self.data_home.mkdir(parents=True)
        link = self.data_home / "glossary.md"
        link.symlink_to(os.path.relpath(target, self.data_home))

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink(), "setup must not replace the symlink")
        expected = self.template_text() + OPERATOR_ENTRIES
        self.assertEqual(target.read_text(encoding="utf-8"), expected)
        # Every term, anti-term, and alias survives byte-for-byte.
        self.assertTrue(target.read_text(encoding="utf-8").endswith(OPERATOR_ENTRIES))
        self.assertIn(
            f"migrated {self.data_home.resolve() / 'glossary.md'} "
            "header to current template",
            result.stdout,
        )
        self.assert_one_complete_block(self.claude, expected)
        self.assert_one_complete_block(self.agents, expected)

        again = self.run_tool("setup")

        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(again.stdout.strip(), "setup already complete")
        self.assertEqual(target.read_bytes(), expected.encode("utf-8"))

    def test_setup_seeds_dangling_symlinked_glossary_through_its_target(self):
        target = self.root / "dotfiles" / "glossary.md"
        target.parent.mkdir(parents=True)
        self.data_home.mkdir(parents=True)
        link = self.data_home / "glossary.md"
        link.symlink_to(os.path.relpath(target, self.data_home))
        # Path.exists() is False for a dangling symlink; the link is still real.
        self.assertFalse(link.exists())

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink(), "setup must not replace the symlink")
        self.assertEqual(target.read_text(encoding="utf-8"), self.template_text())
        self.assertIn(
            f"created {self.data_home.resolve() / 'glossary.md'}", result.stdout
        )
        self.assert_one_complete_block(self.claude, self.template_text())
        self.assert_one_complete_block(self.agents, self.template_text())

    def test_setup_refuses_self_referential_symlinked_glossary(self):
        self.data_home.mkdir(parents=True)
        link = self.data_home / "glossary.md"
        link.symlink_to("glossary.md")
        # On Python 3.14 resolve() returns the link path itself rather than
        # raising, so this must be detected explicitly before any write.
        self.assertTrue(link.is_symlink())
        self.assertFalse(link.exists())

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("self-referential or looping symlink", result.stderr)
        self.assertTrue(link.is_symlink(), "setup must not replace the symlink")
        self.assertFalse(link.is_file())
        self.assertEqual(os.readlink(link), "glossary.md")
        # Refusal happens before any target is written.
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.agents.exists())

    def test_setup_refuses_mutually_looping_symlinked_glossary(self):
        self.data_home.mkdir(parents=True)
        first = self.data_home / "glossary.md"
        second = self.data_home / "other.md"
        first.symlink_to(second.name)
        second.symlink_to(first.name)

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("self-referential or looping symlink", result.stderr)
        self.assertTrue(first.is_symlink(), "setup must not replace the symlink")
        self.assertFalse(first.is_file())
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.agents.exists())

    def test_setup_refuses_symlink_through_regular_file_without_claiming_loop(self):
        self.data_home.mkdir(parents=True)
        plainfile = self.data_home / "plainfile"
        plainfile.write_text("not a directory\n", encoding="utf-8")
        link = self.data_home / "glossary.md"
        link.symlink_to("plainfile/sub")

        result = self.run_tool("setup")

        self.assertEqual(result.returncode, 1, result.stderr)
        # ENOTDIR is a resolution failure, not a symlink loop.
        self.assertNotIn("self-referential", result.stderr)
        self.assertNotIn("looping symlink", result.stderr)
        # The underlying cause is surfaced instead of a loop diagnosis.
        self.assertIn("Not a directory", result.stderr)
        self.assertTrue(link.is_symlink(), "setup must not replace the symlink")
        self.assertFalse(link.is_file())
        self.assertEqual(os.readlink(link), "plainfile/sub")
        # Refusal happens before any target is written.
        self.assertFalse(self.claude.exists())
        self.assertFalse(self.agents.exists())

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


class ManageMissingDefaultTargetsTest(unittest.TestCase):
    """A default target (``--claude-file``/``--agents-file`` left unspecified)
    that doesn't already exist on disk names a harness that isn't installed;
    setup must leave it alone instead of creating it. An explicitly passed
    target is always written, whether or not it already exists."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_home = self.root / "config" / "ai-glossary"
        self.claude = self.root / "claude" / "CLAUDE.md"
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_setup_skips_nonexistent_default_agents_file(self):
        default_agents_file = self.codex_home / "AGENTS.md"
        self.assertFalse(default_agents_file.exists())

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "setup",
                "--data-home",
                str(self.data_home),
                "--claude-file",
                str(self.claude),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "CODEX_HOME": str(self.codex_home)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(default_agents_file.exists())
        self.assertTrue(self.claude.exists())
        block = self.claude.read_text(encoding="utf-8")
        self.assertIn(manage.START, block)
        self.assertNotIn("AGENTS.md", block)
        self.assertNotIn("--agents-file", block)

    def test_setup_writes_explicit_nonexistent_agents_file(self):
        agents = self.root / "codex" / "AGENTS.md"
        self.assertFalse(agents.exists())

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "setup",
                "--data-home",
                str(self.data_home),
                "--claude-file",
                str(self.claude),
                "--agents-file",
                str(agents),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "CODEX_HOME": str(self.codex_home)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(agents.exists())
        self.assertIn(manage.START, agents.read_text(encoding="utf-8"))

    def test_setup_migrates_header_without_active_targets(self):
        self.data_home.mkdir(parents=True)
        glossary_path = self.data_home / "glossary.md"
        glossary_path.write_text(
            STALE_HEADER + OPERATOR_ENTRIES, encoding="utf-8"
        )
        claude_home = self.root / "claude-home"

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "setup",
                "--data-home",
                str(self.data_home),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "HOME": str(self.root / "home"),
                "CLAUDE_CONFIG_DIR": str(claude_home),
                "CODEX_HOME": str(self.codex_home),
            },
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"migrated {glossary_path.resolve()} header to current template",
            result.stdout,
        )
        self.assertEqual(
            glossary_path.read_text(encoding="utf-8"),
            TEMPLATE.read_text(encoding="utf-8") + OPERATOR_ENTRIES,
        )
        self.assertFalse((claude_home / "CLAUDE.md").exists())
        self.assertFalse((self.codex_home / "AGENTS.md").exists())


class SynchronizationGuidanceSingleTargetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_home = self.root / "config" / "ai-glossary"
        self.claude_file = self.root / "claude" / "CLAUDE.md"

    def tearDown(self):
        self.temp.cleanup()

    def test_only_mentions_and_syncs_the_present_target(self):
        guidance = manage.synchronization_guidance(
            self.data_home, self.claude_file, None
        )

        self.assertIn(str(self.claude_file), guidance)
        self.assertNotIn("AGENTS.md", guidance)
        self.assertNotIn("--agents-file", guidance)
        self.assertIn("is a generated copy; never", guidance)
        self.assertNotIn("generated copies; never edit either block", guidance)


if __name__ == "__main__":
    unittest.main()
