"""The suite must never launch the developer's real Obsidian app (#357).

print_save_links() opens each saved note with `open` (macOS) or `xdg-open` (Linux)
unless RESEARCH_AUTOOPEN=0. tests/conftest.py sets it for every test. These tests
put a recording stub opener first on PATH and save a note from a subprocess that
inherits the test environment, the way test_research_deep_fallback.py does."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
OPENER = {"Darwin": "open", "Linux": "xdg-open"}.get(platform.system())

pytestmark = pytest.mark.skipif(
    OPENER is None, reason="Windows opens through cmd /c start, which a PATH stub cannot catch"
)

_PROBE = """
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from research.lib import vault
vault.print_save_links(Path(sys.argv[1]))
"""


def _save_note(tmp_path: Path, env: dict) -> list[str]:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    calls = tmp_path / "calls.txt"
    stub = stub_dir / OPENER
    stub.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\n', encoding="utf-8")
    stub.chmod(0o755)
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Saved.md"
    note.write_text("# Saved\n", encoding="utf-8")
    env = {
        **env,
        "PATH": f"{stub_dir}{os.pathsep}{env.get('PATH', '')}",
        "OBSIDIAN_VAULT_PATH": str(vault),
        "OBSIDIAN_ENV_FILE": str(tmp_path / "missing.env"),
    }
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(note)],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []


def test_a_saved_note_does_not_open_obsidian_during_tests(tmp_path):
    assert _save_note(tmp_path, dict(os.environ)) == []


def test_the_stub_sees_the_opener_when_autoopen_is_on(tmp_path):
    """Control: the same probe with auto-open enabled reaches the stub, so the
    empty list above means "not called", not "stub never wired in"."""
    calls = _save_note(tmp_path, {**os.environ, "RESEARCH_AUTOOPEN": "1"})
    assert len(calls) == 1 and calls[0].startswith("obsidian://")
