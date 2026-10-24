"""scripts/verify_quotes.py: /obsidian-reconcile acts only on contradictions whose
two sides it can quote from the notes. These tests drive the CLI the way the
command does, with a JSON array on stdin."""

from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_quotes.py"

NOTE = (
    "---\ntype: concept\n---\n\n"
    "## For future agent\n\n"
    "Revenue rose 12% in the third quarter of 2026.\n"
    "The pilot uses a local search index.\n"
)


def run(vault: Path, claims) -> tuple[int, list | str]:
    payload = claims if isinstance(claims, str) else json.dumps(claims)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(vault)],
        input=payload.encode("utf-8"),
        capture_output=True,
    )
    out = result.stdout.decode("utf-8")
    return result.returncode, (json.loads(out) if out.strip() else result.stderr.decode())


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "Revenue.md").write_text(NOTE, encoding="utf-8")
    return tmp_path


def claim(quote, line=7, path="notes/Revenue.md"):
    return {"path": path, "line": line, "quote": quote}


def test_a_real_quote_on_its_line_is_proven(vault):
    code, out = run(vault, [claim("Revenue rose 12% in the third quarter")])
    assert code == 0
    assert out[0]["ok"] is True and out[0]["found_line"] == 7 and out[0]["reason"] is None


def test_an_invented_quote_is_not_proven(vault):
    code, out = run(vault, [claim("Revenue doubled after the product launch")])
    assert code == 1
    assert out[0]["ok"] is False and out[0]["reason"] == "quote not found in the note"


def test_one_changed_word_is_not_proven(vault):
    code, out = run(vault, [claim("Revenue fell 12% in the third quarter")])
    assert code == 1 and out[0]["ok"] is False


def test_one_failing_side_fails_the_pair(vault):
    code, out = run(vault, [
        claim("Revenue rose 12% in the third quarter"),
        claim("Revenue fell 12% in the third quarter"),
    ])
    assert code == 1
    assert [c["ok"] for c in out] == [True, False]


def test_a_wrong_line_number_is_corrected_not_failed(vault):
    code, out = run(vault, [claim("The pilot uses a local search index", line=3)])
    assert code == 0
    assert out[0]["found_line"] == 8
    assert out[0]["reason"] == "quote is on line 8, not line 3"


def test_a_short_quote_proves_nothing(vault):
    code, out = run(vault, [claim("Revenue")])
    assert code == 1 and "shorter than 12" in out[0]["reason"]


def test_a_quote_spanning_two_lines_is_refused(vault):
    code, out = run(vault, [claim("third quarter of 2026.\nThe pilot uses")])
    assert code == 1 and out[0]["reason"] == "quote spans more than one line"


def test_a_path_outside_the_vault_is_refused(vault, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "Secret.md").write_text("Revenue rose 12% in the third quarter\n", encoding="utf-8")
    rel = Path("..") / outside.name / "Secret.md"
    code, out = run(vault, [claim("Revenue rose 12% in the third quarter", path=str(rel))])
    assert code == 1 and out[0]["reason"] == "path is outside the vault"


def test_a_missing_note_is_refused(vault):
    code, out = run(vault, [claim("Revenue rose 12% in the third quarter", path="notes/Nope.md")])
    assert code == 1 and out[0]["reason"] == "no such note"


def test_bom_crlf_and_decomposed_unicode_still_match(vault):
    """Notes written on Windows or by macOS tools: a BOM, CRLF line ends, and
    decomposed accents. The quote an agent copies is usually composed. NFC and
    the space collapse are load-bearing here; the BOM is only a guard, since a
    substring match tolerates it either way."""
    text = "Café owners  reported a strong summer season.\r\n"
    nfd = unicodedata.normalize("NFD", text)
    (vault / "notes" / "Cafe.md").write_bytes(b"\xef\xbb\xbf" + nfd.encode("utf-8"))
    code, out = run(vault, [claim("Café owners reported a strong summer", line=1,
                                  path="notes/Cafe.md")])
    assert code == 0 and out[0]["found_line"] == 1


def test_reconcile_proves_contradictions_with_the_checker():
    """Prose contract: the command must keep calling the checker and dropping
    what it cannot prove. A copy edit that removes either breaks this test."""
    text = (SCRIPT.parents[1] / "commands" / "obsidian-reconcile.md").read_text(encoding="utf-8")
    assert "scripts/verify_quotes.py" in text
    assert "drop the contradiction: no rewrite, no conflict note" in text
    assert "Use `found_line` from the output" in text
    assert "**Dropped as unproven**" in text


def test_bad_input_exits_2(vault):
    assert run(vault, "not json")[0] == 2
    assert run(vault, {"path": "notes/Revenue.md"})[0] == 2
