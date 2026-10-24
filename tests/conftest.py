"""Suite-wide fixtures.

research.lib.vault.print_save_links() opens every saved note in Obsidian with
`open` / `xdg-open` / `cmd /c start` unless RESEARCH_AUTOOPEN=0. A test that saves
a note would otherwise launch the developer's real Obsidian app (#357). Setting it
here reaches subprocesses too, since they inherit os.environ.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_obsidian_autoopen(monkeypatch):
    monkeypatch.setenv("RESEARCH_AUTOOPEN", "0")
