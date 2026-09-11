#!/usr/bin/env python3
"""Synchronize the canonical personal glossary into global harness instructions."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Optional

START = "<!-- ai-glossary:managed:start -->"
END = "<!-- ai-glossary:managed:end -->"
LEGACY_IMPORT = re.compile(
    r"^\s*@[^\r\n]*[\\/]ai-glossary[\\/]glossary\.md\s*$"
)
ENTRIES_SEPARATOR = "---"

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


def synchronization_guidance(
    data_home: Path,
    claude_file: Optional[Path],
    agents_file: Optional[Path],
) -> str:
    if claude_file is None and agents_file is None:
        raise ValueError("synchronization_guidance requires at least one target")

    glossary_file = data_home / "glossary.md"
    command_args = [
        sys.executable,
        str(Path(__file__).resolve()),
        "setup",
        "--data-home",
        str(data_home),
    ]
    if claude_file is not None:
        command_args += ["--claude-file", str(claude_file)]
    if agents_file is not None:
        command_args += ["--agents-file", str(agents_file)]
    command = shlex.join(command_args)
    curation_metadata = json.dumps(
        {"canonical_glossary": str(glossary_file), "sync_command": command},
        separators=(",", ":"),
    )

    if claude_file is not None and agents_file is not None:
        peer_prose = (
            f"This managed block in `{claude_file}` and its peer in "
            f"`{agents_file}` are generated copies; never edit either block "
            "directly. After every canonical edit, immediately synchronize "
            "both generated copies by running:"
        )
    else:
        present = claude_file if claude_file is not None else agents_file
        peer_prose = (
            f"This managed block in `{present}` is a generated copy; never "
            "edit it directly. After every canonical edit, immediately "
            "synchronize it by running:"
        )

    return (
        "## Canonical glossary workflow\n\n"
        f"<!-- ai-glossary:curation {curation_metadata} -->\n\n"
        "The canonical editable file is "
        "`$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to "
        "`~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or "
        "empty. For this installation, "
        f"edit `{glossary_file}` to curate terms. "
        f"{peer_prose}\n\n"
        f"```sh\n{command}\n```\n\n"
    )


def managed_block(glossary: str, guidance: str = "") -> str:
    if START in glossary or END in glossary:
        raise ValueError("glossary contains reserved managed-block markers")
    content = glossary if glossary.endswith("\n") else glossary + "\n"
    return f"{START}\n{guidance}{content}{END}\n"


def setup_target(text: str, glossary: str, guidance: str = "") -> str:
    return unmanaged_text(text) + managed_block(glossary, guidance)


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
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def write_if_changed(path: Path, content: str) -> bool:
    if read_target(path) == content:
        return False
    atomic_write(path, content)
    return True


def canonical_glossary_path(glossary_file: Path) -> Path:
    """Return the file setup should write when updating the canonical glossary.

    An operator may symlink ``<data home>/glossary.md`` into a dotfiles repo.
    ``atomic_write`` replaces its target path atomically, which would swap the
    symlink for a regular file and silently detach the real glossary. Writing
    through the resolved symlink target keeps the link intact and edits the file
    it points at. Non-symlink paths are returned unchanged, and a dangling
    symlink still resolves to the target the operator named.

    A symlink that points at itself, or a loop of symlinks, names no real
    target. On Python 3.14 ``Path.resolve()`` returns the link path itself
    instead of raising, so writing "through" it would still replace the link.
    Detect that case by resolving strictly: a missing target raises
    ``FileNotFoundError`` (a dangling link we can still seed), while a loop
    raises ``OSError`` with ``ELOOP`` on Python 3.13+ or ``RuntimeError`` on
    earlier versions. Any other resolution failure -- for example ``ENOTDIR``
    when the link points through a regular file -- is a different error and is
    reported with its underlying cause rather than mislabelled as a loop.
    Refuse every failure rather than detach the link, so the pathological state
    is reported instead of silently replaced.
    """
    if not glossary_file.is_symlink():
        return glossary_file
    try:
        return glossary_file.resolve(strict=True)
    except FileNotFoundError:
        return glossary_file.resolve()
    except (OSError, RuntimeError) as error:
        # Only ELOOP (or the pre-3.13 RuntimeError signalling it) means the
        # link loops. Every other OSError -- ENOTDIR, EACCES, ... -- has a
        # different cause and must not be reported as a symlink loop.
        is_loop = isinstance(error, RuntimeError) or getattr(
            error, "errno", None
        ) == errno.ELOOP
        if is_loop:
            raise ValueError(
                f"{glossary_file} is a self-referential or looping symlink "
                "with no real target; refusing to replace it with a regular "
                "file"
            ) from error
        raise ValueError(
            f"{glossary_file} cannot be resolved to a real target: {error}; "
            "refusing to replace it with a regular file"
        ) from error


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_glossary_header(text: str) -> Optional[tuple[str, str]]:
    """Split a glossary into its tool-owned header region and operator body.

    The header region runs from the start of the file through the first line
    whose content is exactly ``---`` (the entries separator), inclusive. The
    body is everything after it. Returns ``None`` when the file carries no
    entries separator, so a file that is not a seeded glossary is never
    rewritten.
    """
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.rstrip("\r\n") == ENTRIES_SEPARATOR:
            end = offset + len(line)
            return text[:end], text[end:]
        offset += len(line)
    return None


def migrate_glossary_header(text: str, template: str) -> Optional[str]:
    """Replace a stale tool-owned header region with the template's.

    Returns ``None`` when there is nothing to do: the file has no entries
    separator (so it cannot be confidently identified as a seeded glossary),
    or its header already matches the template modulo line endings. Operator
    entries after the separator are preserved byte-for-byte.
    """
    canonical = split_glossary_header(text)
    current = split_glossary_header(template)
    if canonical is None or current is None:
        return None
    canonical_header, body = canonical
    template_header, _ = current
    if _normalize_newlines(canonical_header) == _normalize_newlines(template_header):
        return None
    # Match the canonical file's own line-ending style so the migrated header
    # does not introduce a foreign ending into an otherwise CRLF file.
    newline = "\r\n" if "\r\n" in text else "\n"
    migrated_header = _normalize_newlines(template_header).replace("\n", newline)
    return migrated_header + body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "uninstall"))
    parser.add_argument("--data-home", type=Path, default=default_data_home())
    parser.add_argument("--claude-file", type=Path, default=None)
    parser.add_argument("--agents-file", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_home = args.data_home.expanduser().resolve()
    glossary_file = data_home / "glossary.md"
    template = Path(__file__).resolve().parent / "templates" / "glossary.md"
    claude_explicit = args.claude_file is not None
    agents_explicit = args.agents_file is not None
    claude_file = (
        args.claude_file if claude_explicit else default_claude_file()
    ).expanduser().resolve()
    agents_file = (
        args.agents_file if agents_explicit else default_agents_file()
    ).expanduser().resolve()
    targets = (claude_file, agents_file)
    try:
        changes: list[str] = []
        if args.action == "setup":
            # Write through a symlinked canonical glossary (often pointing into
            # a dotfiles repo) instead of replacing the link with a regular
            # file. A symlink that cannot be resolved to a real target -- a
            # loop or any other resolution failure -- raises ValueError here,
            # which the handler below reports.
            glossary_write_path = canonical_glossary_path(glossary_file)
            data_home.mkdir(parents=True, exist_ok=True)
            template_text = template.read_text(encoding="utf-8")
            if not glossary_file.exists():
                atomic_write(glossary_write_path, template_text)
                changes.append(f"created {glossary_file}")
            glossary = read_target(glossary_file)
            migrated = migrate_glossary_header(glossary, template_text)
            if migrated is not None:
                atomic_write(glossary_write_path, migrated)
                glossary = migrated
                changes.append(
                    f"migrated {glossary_file} header to current template"
                )
            active_targets = tuple(
                target
                for target, is_explicit in (
                    (claude_file, claude_explicit),
                    (agents_file, agents_explicit),
                )
                if is_explicit or target.exists()
            )
            guidance_targets = (
                claude_file if claude_explicit or claude_file.exists() else None,
                agents_file if agents_explicit or agents_file.exists() else None,
            )
            updates = {}
            if active_targets:
                guidance = synchronization_guidance(data_home, *guidance_targets)
                updates = {
                    target: setup_target(read_target(target), glossary, guidance)
                    for target in active_targets
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
