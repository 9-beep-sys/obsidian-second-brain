"""Runtime tests for the Hermes vault-maintenance hook (#345).

Hermes fires `on_session_end` after every turn, and a `hermes -z` started by the
hook fires it again, so the hook must be registered on `on_session_finalize`
and must not start a second consolidation while one is running.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from _bash import BASH

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "hooks" / "obsidian-hermes-session-end.sh"
CONFIG = REPO_ROOT / "hooks" / "hermes-hooks.config.example.yaml"


def _stub(tmp_path: Path, sleep: float = 0.0) -> Path:
    stub = tmp_path / "consolidate.sh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "run $$" >> "{tmp_path}/runs.txt"\n'
        f"sleep {sleep}\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _run(payload: dict, tmp_path: Path, stub: Path, **extra) -> subprocess.CompletedProcess:
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    env = {**os.environ,
           "OBSIDIAN_VAULT_PATH": str(vault),
           "OBSIDIAN_HERMES_HOOK_ENABLED": "1",
           "OBSIDIAN_HERMES_CONSOLIDATE_CMD": str(stub),
           "TMPDIR": str(tmp_path)}
    env.update(extra)
    return subprocess.run([BASH, str(HOOK)], input=json.dumps(payload), env=env,
                          capture_output=True, text=True, timeout=30)


def _runs(tmp_path: Path, expect: int, wait: float = 3.0) -> int:
    f = tmp_path / "runs.txt"
    end = time.time() + wait
    while time.time() < end:
        if f.exists() and len(f.read_text().splitlines()) >= expect:
            break
        time.sleep(0.05)
    time.sleep(0.3)
    return len(f.read_text().splitlines()) if f.exists() else 0


def test_registered_on_session_finalize_not_session_end():
    text = CONFIG.read_text(encoding="utf-8")
    keys = [l.strip() for l in text.splitlines() if l.startswith("  on_session")]
    assert keys == ["on_session_finalize:"]


def test_single_session_starts_consolidation(tmp_path):
    r = _run({"session_id": "s1"}, tmp_path, _stub(tmp_path))
    assert r.returncode == 0 and r.stdout.strip() == "{}"
    assert _runs(tmp_path, 1) == 1


def test_no_second_consolidation_while_one_runs(tmp_path):
    stub = _stub(tmp_path, sleep=2)
    _run({"session_id": "s1"}, tmp_path, stub)
    assert _runs(tmp_path, 1) == 1
    # The consolidation's own `hermes -z` run fires the hook again.
    r = _run({"session_id": "s2"}, tmp_path, stub)
    assert r.returncode == 0 and r.stdout.strip() == "{}"
    assert _runs(tmp_path, 2, wait=1.0) == 1


def test_env_marker_guard(tmp_path):
    r = _run({"session_id": "s1"}, tmp_path, _stub(tmp_path),
             OBSIDIAN_HERMES_CONSOLIDATING="1")
    assert r.returncode == 0 and r.stdout.strip() == "{}"
    assert _runs(tmp_path, 1, wait=1.0) == 0


def test_lock_released_after_consolidation(tmp_path):
    stub = _stub(tmp_path)
    _run({"session_id": "s1"}, tmp_path, stub)
    assert _runs(tmp_path, 1) == 1
    time.sleep(0.5)
    _run({"session_id": "s2"}, tmp_path, stub)
    assert _runs(tmp_path, 2) == 2
