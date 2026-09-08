#!/usr/bin/env python3
"""Synchronize the canonical personal glossary into global harness instructions."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is POSIX-only
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curation  # noqa: E402

START = "<!-- ai-glossary:managed:start -->"
END = "<!-- ai-glossary:managed:end -->"
LEGACY_IMPORT = re.compile(
    r"^\s*@[^\r\n]*[\\/]ai-glossary[\\/]glossary\.md\s*$"
)

CLAUDE_HOOK_EVENT = "SessionEnd"
OPENCODE_PLUGIN_NAME = "ai-glossary-curate.js"
OPENCODE_PLUGIN_MARKER = "Managed by ai-glossary-setup"


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
    data_home: Path, claude_file: Path, agents_file: Path
) -> str:
    glossary_file = data_home / "glossary.md"
    command_args = (
        sys.executable,
        str(Path(__file__).resolve()),
        "setup",
        "--data-home",
        str(data_home),
        "--claude-file",
        str(claude_file),
        "--agents-file",
        str(agents_file),
    )
    command = shlex.join(command_args)
    curation_metadata = json.dumps(
        {"canonical_glossary": str(glossary_file), "sync_command": command},
        separators=(",", ":"),
    )
    return (
        "## Canonical glossary workflow\n\n"
        f"<!-- ai-glossary:curation {curation_metadata} -->\n\n"
        "The canonical editable file is "
        "`$XDG_CONFIG_HOME/ai-glossary/glossary.md`, falling back to "
        "`~/.config/ai-glossary/glossary.md` when `XDG_CONFIG_HOME` is unset or "
        "empty. For this installation, "
        f"edit `{glossary_file}` to curate terms. "
        f"This managed block in `{claude_file}` and its peer in `{agents_file}` are "
        "generated copies; never edit either block directly. After every canonical "
        "edit, immediately synchronize both generated copies by running:\n\n"
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


# ---------------------------------------------------------------------------
# Automatic-curation action: shared engine invoked by both harness adapters
# ---------------------------------------------------------------------------


class _LockFile:
    """Advisory exclusive lock held around the canonical read-modify-write
    and synchronization sequence, so concurrent curation invocations from
    different sessions serialize instead of racing each other."""

    def __init__(self, path: Path):
        self._path = path
        self._handle = None

    def __enter__(self) -> "_LockFile":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self._path, "a+")
        if fcntl is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._handle is not None:
            if fcntl is not None:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def curate_from_messages(
    data_home: Path,
    claude_file: Path,
    agents_file: Path,
    messages: list[str],
    min_repetitions: int = curation.DEFAULT_MIN_REPETITIONS,
) -> list[curation.AppliedChange]:
    """Run one automatic-curation pass against the canonical glossary and
    synchronize both managed copies. Holds an advisory lock for the entire
    read-candidate-write-sync sequence so a concurrent invocation from
    another session cannot interleave and lose an update.

    Returns the list of changes actually applied (empty when there was
    nothing new to add)."""

    data_home.mkdir(parents=True, exist_ok=True)
    glossary_file = data_home / "glossary.md"
    lock_file = data_home / ".curate.lock"
    template = Path(__file__).resolve().parent / "templates" / "glossary.md"
    targets = (claude_file, agents_file)

    with _LockFile(lock_file):
        if not glossary_file.exists():
            atomic_write(glossary_file, template.read_text(encoding="utf-8"))
        current = glossary_file.read_text(encoding="utf-8")

        candidates = curation.find_candidates(messages, min_repetitions=min_repetitions)
        updated_text, applied = curation.apply_candidates(current, candidates)

        if applied:
            atomic_write(glossary_file, updated_text)
            guidance = synchronization_guidance(data_home, *targets)
            for target in targets:
                updated_target = setup_target(read_target(target), updated_text, guidance)
                write_if_changed(target, updated_target)

    return applied


def _read_curate_input(args: argparse.Namespace) -> list[str]:
    """Resolve operator messages for the ``curate`` action.

    Claude Code's SessionEnd command hook receives a JSON envelope on
    stdin (``{"transcript_path": ..., "hook_event_name": "SessionEnd", ...}``);
    the actual JSONL transcript lives at that path and is read separately.
    The Opencode plugin instead pipes the session's own message list
    directly as JSON. ``--transcript`` is available for direct invocation
    (testing, or a caller that already has a file path) and, for
    ``--source claude``, is treated as the JSONL transcript path itself
    rather than an envelope."""

    if args.source == "claude":
        if args.transcript:
            raw_text = Path(args.transcript).expanduser().read_text(encoding="utf-8")
        else:
            envelope_text = sys.stdin.read()
            try:
                envelope = json.loads(envelope_text)
            except (ValueError, TypeError):
                envelope = None
            transcript_path = (
                envelope.get("transcript_path") if isinstance(envelope, dict) else None
            )
            if transcript_path:
                raw_text = Path(transcript_path).expanduser().read_text(encoding="utf-8")
            else:
                # Fall back to treating the stdin payload itself as the
                # transcript, for direct/manual invocation without a hook
                # envelope.
                raw_text = envelope_text
        return curation.extract_operator_messages_claude(raw_text)

    if args.source == "opencode":
        if args.transcript:
            raw_text = Path(args.transcript).expanduser().read_text(encoding="utf-8")
        else:
            raw_text = sys.stdin.read()
        try:
            payload = json.loads(raw_text)
        except (ValueError, TypeError):
            payload = raw_text
        return curation.extract_operator_messages_opencode(payload)

    if args.transcript:
        raw_text = Path(args.transcript).expanduser().read_text(encoding="utf-8")
    else:
        raw_text = sys.stdin.read()
    return curation.sniff_and_extract(raw_text)


# ---------------------------------------------------------------------------
# Claude Code SessionEnd hook lifecycle management
# ---------------------------------------------------------------------------

CLAUDE_HOOK_MARKER = "ai-glossary-setup"


def _default_claude_settings_file() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config).expanduser() if config else Path.home() / ".claude") / "settings.json"


def _curate_hook_command(data_home: Path, claude_file: Path, agents_file: Path) -> str:
    """Command run by the managed SessionEnd hook. Claude Code delivers the
    hook's JSON envelope (which carries ``transcript_path``) on the
    subprocess's stdin automatically; no argument or template substitution
    is needed to receive it."""

    manage_path = Path(__file__).resolve()
    command_args = (
        sys.executable,
        str(manage_path),
        "curate",
        "--data-home",
        str(data_home),
        "--claude-file",
        str(claude_file),
        "--agents-file",
        str(agents_file),
        "--source",
        "claude",
    )
    return shlex.join(command_args)


def _load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def _write_json_object(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


def install_claude_hook(
    settings_file: Path, data_home: Path, claude_file: Path, agents_file: Path
) -> bool:
    """Idempotently register the SessionEnd hook that invokes automatic
    curation, preserving every other hook and unrelated settings content."""

    settings = _load_json_object(settings_file)
    hooks = settings.setdefault("hooks", {})
    session_end = hooks.setdefault(CLAUDE_HOOK_EVENT, [])

    command = _curate_hook_command(data_home, claude_file, agents_file)
    handler = {
        "type": "command",
        "command": command,
    }

    for group in session_end:
        for existing_hook in group.get("hooks", []):
            if existing_hook.get("_managed_by") == CLAUDE_HOOK_MARKER:
                if existing_hook.get("command") == command:
                    return False
                existing_hook["command"] = command
                _write_json_object(settings_file, settings)
                return True

    handler["_managed_by"] = CLAUDE_HOOK_MARKER
    session_end.append({"hooks": [handler]})
    _write_json_object(settings_file, settings)
    return True


def uninstall_claude_hook(settings_file: Path) -> bool:
    """Remove only the managed SessionEnd hook entry, preserving every other
    hook and unrelated settings content."""

    if not settings_file.exists():
        return False
    settings = _load_json_object(settings_file)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    session_end = hooks.get(CLAUDE_HOOK_EVENT)
    if not isinstance(session_end, list):
        return False

    changed = False
    remaining_groups = []
    for group in session_end:
        original_hooks = group.get("hooks", [])
        remaining_hooks = [
            hook for hook in original_hooks if hook.get("_managed_by") != CLAUDE_HOOK_MARKER
        ]
        if len(remaining_hooks) != len(original_hooks):
            changed = True
        if remaining_hooks or not original_hooks:
            # Keep the group: either it still has hooks of its own, or it
            # was already empty before we touched it (nothing to drop).
            remaining_groups.append({**group, "hooks": remaining_hooks})
        # else: the group only ever contained our managed hook; drop it.

    if not changed:
        return False

    if remaining_groups:
        hooks[CLAUDE_HOOK_EVENT] = remaining_groups
    else:
        del hooks[CLAUDE_HOOK_EVENT]
    if not hooks:
        del settings["hooks"]

    _write_json_object(settings_file, settings)
    return True


# ---------------------------------------------------------------------------
# Opencode lifecycle plugin management
# ---------------------------------------------------------------------------


def _default_opencode_plugin_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    config_dir = Path(base).expanduser() / "opencode" if base else Path.home() / ".config" / "opencode"
    return config_dir / "plugin"


def _opencode_plugin_source(data_home: Path, claude_file: Path, agents_file: Path) -> str:
    manage_path = Path(__file__).resolve()
    return (
        f"// {OPENCODE_PLUGIN_MARKER}\n"
        "// Invokes the shared ai-glossary automatic-curation command when a\n"
        "// session becomes idle, passing the session's own messages so only\n"
        "// operator-authored text is ever considered as curation evidence.\n"
        "export const AiGlossaryCurate = async ({ client }) => {\n"
        "  return {\n"
        "    event: async ({ event }) => {\n"
        "      if (event.type !== \"session.idle\") return;\n"
        "      const sessionID = event.properties.sessionID;\n"
        "      const response = await client.session.messages({ path: { id: sessionID } });\n"
        "      const payload = JSON.stringify({ messages: response.data ?? response });\n"
        "      await new Promise((resolve, reject) => {\n"
        "        const { spawn } = require(\"node:child_process\");\n"
        f"        const child = spawn({json.dumps(sys.executable)}, [\n"
        f"          {json.dumps(str(manage_path))},\n"
        "          \"curate\",\n"
        f"          \"--data-home\", {json.dumps(str(data_home))},\n"
        f"          \"--claude-file\", {json.dumps(str(claude_file))},\n"
        f"          \"--agents-file\", {json.dumps(str(agents_file))},\n"
        "          \"--source\", \"opencode\",\n"
        "        ]);\n"
        "        child.stdin.write(payload);\n"
        "        child.stdin.end();\n"
        "        child.on(\"error\", reject);\n"
        "        child.on(\"exit\", () => resolve());\n"
        "      });\n"
        "    },\n"
        "  };\n"
        "};\n"
    )


def install_opencode_plugin(
    plugin_dir: Path, data_home: Path, claude_file: Path, agents_file: Path
) -> bool:
    """Idempotently install the dedicated Opencode plugin file, never
    touching unrelated files in the plugin directory."""

    plugin_file = plugin_dir / OPENCODE_PLUGIN_NAME
    source = _opencode_plugin_source(data_home, claude_file, agents_file)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return write_if_changed(plugin_file, source)


def uninstall_opencode_plugin(plugin_dir: Path) -> bool:
    """Remove only the managed plugin file, preserving every other plugin in
    the directory."""

    plugin_file = plugin_dir / OPENCODE_PLUGIN_NAME
    if not plugin_file.exists():
        return False
    text = plugin_file.read_text(encoding="utf-8")
    if OPENCODE_PLUGIN_MARKER not in text:
        # Something else occupies our filename; leave it alone.
        return False
    plugin_file.unlink()
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "uninstall", "curate"))
    parser.add_argument("--data-home", type=Path, default=default_data_home())
    parser.add_argument("--claude-file", type=Path, default=default_claude_file())
    parser.add_argument("--agents-file", type=Path, default=default_agents_file())
    parser.add_argument(
        "--claude-settings-file", type=Path, default=_default_claude_settings_file()
    )
    parser.add_argument(
        "--opencode-plugin-dir", type=Path, default=_default_opencode_plugin_dir()
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Path to a Claude Code transcript or Opencode message export. "
        "Reads standard input when omitted.",
    )
    parser.add_argument(
        "--source",
        choices=("claude", "opencode", "auto"),
        default="auto",
        help="Transcript format. Defaults to best-effort auto-detection.",
    )
    parser.add_argument(
        "--min-repetitions",
        type=int,
        default=curation.DEFAULT_MIN_REPETITIONS,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_home = args.data_home.expanduser().resolve()
    glossary_file = data_home / "glossary.md"
    template = Path(__file__).resolve().parent / "templates" / "glossary.md"
    targets = tuple(
        path.expanduser().resolve() for path in (args.claude_file, args.agents_file)
    )
    claude_settings_file = args.claude_settings_file.expanduser().resolve()
    opencode_plugin_dir = args.opencode_plugin_dir.expanduser().resolve()

    try:
        if args.action == "curate":
            messages = _read_curate_input(args)
            applied = curate_from_messages(
                data_home,
                targets[0],
                targets[1],
                messages,
                min_repetitions=args.min_repetitions,
            )
            if applied:
                for change in applied:
                    print(f"added {change.term}: {change.meaning}")
            else:
                print("no qualifying automatic-curation candidates found")
            return 0

        changes: list[str] = []
        if args.action == "setup":
            data_home.mkdir(parents=True, exist_ok=True)
            if not glossary_file.exists():
                atomic_write(glossary_file, template.read_text(encoding="utf-8"))
                changes.append(f"created {glossary_file}")
            glossary = glossary_file.read_text(encoding="utf-8")
            guidance = synchronization_guidance(data_home, *targets)
            updates = {
                target: setup_target(read_target(target), glossary, guidance)
                for target in targets
            }
            for target, updated in updates.items():
                if write_if_changed(target, updated):
                    changes.append(f"synchronized {target}")
            if install_claude_hook(claude_settings_file, data_home, *targets):
                changes.append(f"installed Claude Code SessionEnd hook in {claude_settings_file}")
            if install_opencode_plugin(opencode_plugin_dir, data_home, *targets):
                changes.append(
                    f"installed Opencode curation plugin in {opencode_plugin_dir / OPENCODE_PLUGIN_NAME}"
                )
        else:
            existing_targets = tuple(target for target in targets if target.exists())
            updates = {
                target: unmanaged_text(read_target(target)) for target in existing_targets
            }
            for target, updated in updates.items():
                if write_if_changed(target, updated):
                    changes.append(f"removed managed glossary from {target}")
            if uninstall_claude_hook(claude_settings_file):
                changes.append(f"removed Claude Code SessionEnd hook from {claude_settings_file}")
            if uninstall_opencode_plugin(opencode_plugin_dir):
                changes.append(
                    f"removed Opencode curation plugin from {opencode_plugin_dir / OPENCODE_PLUGIN_NAME}"
                )

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
