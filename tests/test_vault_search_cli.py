"""Standalone search uses the real vault implementation and synthetic notes."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "vault_search.py"


def run_cli(tmp_path, *args, vault=True):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "USERPROFILE": str(home),
        "OBSIDIAN_ENV_FILE": str(home / "missing.env"),
        "OBSIDIAN_SEARCH_SEMANTIC": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if vault:
        notes = tmp_path / "vault"
        notes.mkdir(exist_ok=True)
        (notes / "Synthetic.md").write_text(
            "# Synthetic\nOrchid project status is ready.\n", encoding="utf-8"
        )
        env["OBSIDIAN_VAULT_PATH"] = str(notes)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_json_result(tmp_path):
    result = run_cli(tmp_path, "orchid", "--limit", "1", "--lexical")
    assert result.returncode == 0, result.stderr
    hits = json.loads(result.stdout)
    assert len(hits) == 1
    assert hits[0]["path"] == "Synthetic.md"
    assert set(hits[0]) == {"path", "title", "snippet"}


def test_empty_result(tmp_path):
    result = run_cli(tmp_path, "unfindableword", "--lexical")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_missing_vault(tmp_path):
    result = run_cli(tmp_path, "orchid", vault=False)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "OBSIDIAN_VAULT_PATH" in result.stderr


def test_invalid_limit(tmp_path):
    result = run_cli(tmp_path, "orchid", "--limit", "nope")
    assert result.returncode == 2
    assert "invalid int value" in result.stderr


def test_semantic_dispatch(monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("vault_search_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.osb_env, "vault_path", lambda: "/synthetic")
    calls = []
    monkeypatch.setattr(module.vault_ops, "search", lambda q, **kw: calls.append(kw) or [])
    assert module.main(["orchid"]) == 0
    assert module.main(["orchid", "--lexical", "--limit", "2"]) == 0
    assert calls == [{"limit": 6, "semantic": None}, {"limit": 2, "semantic": False}]
    assert capsys.readouterr().out == "[]\n[]\n"
