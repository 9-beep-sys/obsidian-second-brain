"""A freshly bootstrapped vault must read clean in the MCP health check too (#344)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "integrations" / "obsidian-mcp-server"))


@pytest.mark.parametrize("preset", ["executive", "default"])
def test_fresh_bootstrap_has_no_wanted_notes_or_orphans(tmp_path, monkeypatch, preset):
    vault = tmp_path / "vault"
    subprocess.run(
        [sys.executable, "scripts/bootstrap_vault.py", "--path", str(vault),
         "--name", "Test", "--preset", preset],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault))
    import vault_ops
    importlib.reload(vault_ops)
    health = vault_ops.vault_health()
    assert health["wanted_notes"]["count"] == 0, health["wanted_notes"]["sample"]
    assert health["orphans"]["count"] == 0, health["orphans"]["sample"]


def test_home_has_no_escaped_pipe_outside_a_table_and_no_folder_links(tmp_path):
    vault = tmp_path / "vault"
    subprocess.run(
        [sys.executable, "scripts/bootstrap_vault.py", "--path", str(vault),
         "--name", "Test", "--preset", "executive"],
        cwd=REPO_ROOT, check=True, capture_output=True,
    )
    for line in (vault / "Home.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            assert "\\|" not in line, line
        assert "/]]" not in line and "/\\|" not in line, line


def test_health_resolves_escaped_pipe_and_reports_folder_links(tmp_path, monkeypatch):
    (tmp_path / "Target.md").write_text("---\ntype: x\n---\n# Target\n", encoding="utf-8")
    (tmp_path / "Table.md").write_text(
        "---\ntype: x\n---\n| a |\n|---|\n| [[Target\\|alias]] |\n\n[[Daily/|Daily]]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    import vault_ops
    importlib.reload(vault_ops)
    assert vault_ops._wikilinks("| [[Target\\|alias]] |") == ["Target"]
    health = vault_ops.vault_health()
    assert [w["link"] for w in health["wanted_notes"]["sample"]] == ["Daily/"]
    assert health["orphans"]["count"] == 0
