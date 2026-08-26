#!/usr/bin/env python3
"""Synchronize the canonical personal glossary into global harness instructions."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

START = "<!-- ai-glossary:managed:start -->"
END = "<!-- ai-glossary:managed:end -->"
LEGACY_IMPORT = re.compile(
    r"^\s*@[^\r\n]*[\\/]ai-glossary[\\/]glossary\.md\s*$"
)


def default_data_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base).expanduser() / "ai-glossary" if base else Path.home() / ".config" / "ai-glossary"


def default_claude_file() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "CLAUDE.md"


def default_agents_file() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home).expanduser() if codex_home else Path.home() / ".codex") / "AGENTS.md"


def remove_managed_blocks(text: str) -> str:
    """Remove every complete managed block, rejecting ambiguous partial blocks."""
    output: list[str] = []
    cursor = 0
    while True:
        start = text.find(START, cursor)
        end_without_start = text.find(END, cursor)
        if start == -1:
            if end_without_start != -1:
                raise ValueError(f"found {END!r} without a matching start marker")
            output.append(text[cursor:])
            break
        if end_without_start != -1 and end_without_start < start:
            raise ValueError(f"found {END!r} before a matching start marker")
        output.append(text[cursor:start])
        end = text.find(END, start + len(START))
        nested = text.find(START, start + len(START), end if end != -1 else None)
        if end == -1:
            raise ValueError(f"found {START!r} without a matching end marker")
        if nested != -1:
            raise ValueError("found nested managed-block start markers")
        cursor = end + len(END)
        if text.startswith("\r\n", cursor):
            cursor += 2
        elif text.startswith("\n", cursor):
            cursor += 1
    return "".join(output)


def remove_legacy_imports(text: str) -> str:
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not LEGACY_IMPORT.fullmatch(line.rstrip("\r\n"))
    )


def unmanaged_text(text: str) -> str:
    return remove_legacy_imports(remove_managed_blocks(text))


def managed_block(glossary: str) -> str:
    if START in glossary or END in glossary:
        raise ValueError("glossary contains reserved managed-block markers")
    content = glossary if glossary.endswith("\n") else glossary + "\n"
    return f"{START}\n{content}{END}\n"


def setup_target(text: str, glossary: str) -> str:
    return unmanaged_text(text) + managed_block(glossary)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        if mode is not None:
            os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def read_target(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_if_changed(path: Path, content: str) -> bool:
    if read_target(path) == content:
        return False
    atomic_write(path, content)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "uninstall"))
    parser.add_argument("--data-home", type=Path, default=default_data_home())
    parser.add_argument("--claude-file", type=Path, default=default_claude_file())
    parser.add_argument("--agents-file", type=Path, default=default_agents_file())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_home = args.data_home.expanduser().resolve()
    glossary_file = data_home / "glossary.md"
    template = Path(__file__).resolve().parent / "templates" / "glossary.md"
    targets = (args.claude_file.expanduser(), args.agents_file.expanduser())

    try:
        changes: list[str] = []
        if args.action == "setup":
            data_home.mkdir(parents=True, exist_ok=True)
            if not glossary_file.exists():
                atomic_write(glossary_file, template.read_text(encoding="utf-8"))
                changes.append(f"created {glossary_file}")
            glossary = glossary_file.read_text(encoding="utf-8")
            updates = {
                target: setup_target(read_target(target), glossary) for target in targets
            }
            for target, updated in updates.items():
                if write_if_changed(target, updated):
                    changes.append(f"synchronized {target}")
        else:
            existing_targets = tuple(target for target in targets if target.exists())
            updates = {
                target: unmanaged_text(read_target(target)) for target in existing_targets
            }
            for target, updated in updates.items():
                if write_if_changed(target, updated):
                    changes.append(f"removed managed glossary from {target}")

        if changes:
            print("\n".join(changes))
        elif args.action == "setup":
            print("setup already complete")
        else:
            print("no managed glossary content found")
        if args.action == "uninstall":
            print(f"glossary retained at {glossary_file}")
        return 0
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ai-glossary setup failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
