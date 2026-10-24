"""scripts/checkin.py and scripts/check_notes.py: /obsidian-checkin asks the owner
whether old notes still hold, and hook-less hosts get the write-time check.
These drive both CLIs the way the command does."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from _bash import BASH

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CHECKIN = SCRIPTS / "checkin.py"
CHECK_NOTES = SCRIPTS / "check_notes.py"
TODAY = "2026-10-24"


def note(fm: str, body: str = "## For future agent\nA person.\n\n- Lives in Lisbon\n") -> str:
    return f"---\n{fm}\ntags: [person]\nai-first: true\n---\n\n{body}"


def checkin(vault: Path, *args: str, today: str = TODAY) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(CHECKIN), "--path", str(vault), "--today", today, *args],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout, r.stderr


def picked(vault: Path, *args: str) -> list[str]:
    code, out, err = checkin(vault, "pick", *args)
    assert code == 0, err
    return [c["note"] for c in json.loads(out)]


@pytest.fixture
def vault(tmp_path):
    people = tmp_path / "people"
    people.mkdir()
    (people / "Ana.md").write_text(note("date: 2026-01-10\ntype: person"), encoding="utf-8")
    (people / "Mum.md").write_text(
        note("date: 2026-03-01\ntype: person").replace("tags: [person]", "tags: [person, family]"),
        encoding="utf-8")
    (people / "Fresh.md").write_text(note("date: 2026-10-20\ntype: person"), encoding="utf-8")
    (people / "Gone.md").write_text(note("date: 2026-01-01\ntype: person\nstatus: archived"),
                                    encoding="utf-8")
    (people / "Quiet.md").write_text(note("date: 2026-01-01\ntype: person\ncheckin: never"),
                                     encoding="utf-8")
    return tmp_path


def test_pick_puts_family_first_and_skips_fresh_closed_and_opted_out(vault):
    assert picked(vault) == ["people/Mum.md", "people/Ana.md"]


def test_last_checked_beats_a_newer_updated_and_updated_beats_date(vault):
    ana = vault / "people" / "Ana.md"
    ana.write_text(note("date: 2026-01-10\nupdated: 2026-10-20\ntype: person"), encoding="utf-8")
    assert "people/Ana.md" not in picked(vault)
    ana.write_text(note("date: 2026-01-10\nupdated: 2026-10-20\nlast-checked: 2026-05-01\n"
                        "type: person"), encoding="utf-8")
    assert "people/Ana.md" in picked(vault)


def test_pick_never_holds_more_than_max_open(vault):
    assert checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")[0] == 0
    assert picked(vault, "--max-open", "1") == []
    assert picked(vault, "--max-open", "2") == ["people/Mum.md"]


def test_reminders_repeat_the_full_card_until_answered(vault):
    checkin(vault, "ask", "--note", "people/Mum.md", "--fact", "Lives in Porto", "--fact", "Retired")
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    first = checkin(vault, "message")[1]
    assert first.startswith("Vault check-in: 2 notes to confirm")
    assert "**1. Mum** (facts from 1 Mar)" in first and "- Retired" in first
    again = checkin(vault, "message", today="2026-10-25")[1]
    assert again.startswith("Reminder 1: still waiting on 2 notes")
    assert "- Lives in Porto" in again and "- Lives in Lisbon" in again


def test_peek_renders_without_counting_a_send(vault):
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message", "--peek")
    assert checkin(vault, "message")[1].startswith("Vault check-in")


def test_done_same_stamps_last_checked_and_keeps_the_rest_byte_exact(vault):
    ana = vault / "people" / "Ana.md"
    ana.write_bytes(note("date: 2026-01-10\ntype: person").replace("\n", "\r\n").encode())
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message")
    code, out, err = checkin(vault, "done", "--number", "1", "--outcome", "same")
    assert code == 0, err
    assert json.loads(out)["open_left"] == 0
    raw = ana.read_bytes().decode()
    assert "date: 2026-01-10\r\nlast-checked: 2026-10-24\r\ntype: person" in raw
    assert "\n" not in raw.replace("\r\n", "")
    assert checkin(vault, "message")[1].strip() == ""


def test_skip_closes_without_a_stamp_and_waits_out_the_window(vault):
    checkin(vault, "ask", "--note", "people/Ana.md", "--fact", "Lives in Lisbon")
    checkin(vault, "message")
    checkin(vault, "done", "--number", "1", "--outcome", "skipped")
    assert "last-checked" not in (vault / "people" / "Ana.md").read_text(encoding="utf-8")
    assert "people/Ana.md" not in picked(vault)
    code, out, _ = checkin(vault, "pick", today="2026-11-10")
    assert "people/Ana.md" in [c["note"] for c in json.loads(out)]


def test_a_corrupt_queue_stops_the_run_instead_of_dropping_open_questions(vault):
    (vault / ".checkin.json").write_text("{not json", encoding="utf-8")
    code, _, err = checkin(vault, "message")
    assert code != 0 and "not valid JSON" in err
    assert (vault / ".checkin.json").read_text(encoding="utf-8") == "{not json"


def test_ask_refuses_more_than_three_facts(vault):
    facts = [a for f in ("a", "b", "c", "d") for a in ("--fact", f)]
    code, _, err = checkin(vault, "ask", "--note", "people/Ana.md", *facts)
    assert code != 0 and "1 to 3 facts" in err


# check_notes.py

GOOD = (
    "---\ndate: 2026-10-24\ntype: idea\ntags: [idea]\nai-first: true\n---\n\n"
    "## For future agent\nA note \u2014 with a dash, a [[A\u2014B]] link.\n"
    "\u4e2d\u6587\u2014\u2014\u7834\u6298\u53f7\n"
)


def check(vault: Path, *args: str) -> tuple[int, dict]:
    r = subprocess.run([sys.executable, str(CHECK_NOTES), "--path", str(vault), *args],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_check_notes_fails_then_fix_rewrites_prose_only(tmp_path):
    (tmp_path / "n.md").write_text(GOOD, encoding="utf-8")
    code, out = check(tmp_path, "n.md")
    assert code == 1 and out["failed"][0]["path"] == "n.md"
    code, out = check(tmp_path, "--fix", "n.md")
    text = (tmp_path / "n.md").read_text(encoding="utf-8")
    assert code == 0 and out["fixed"] == ["n.md"], out
    assert "A note - with a dash" in text
    assert "[[A\u2014B]]" in text
    assert "\u4e2d\u6587\u2014\u2014" in text


@pytest.mark.skipif(BASH == "bash", reason="needs bash on PATH for the hook")
def test_check_notes_reports_what_it_cannot_fix(tmp_path):
    (tmp_path / "bare.md").write_text("# Bare\n\nNo frontmatter.\n", encoding="utf-8")
    code, out = check(tmp_path, "--fix", "bare.md")
    assert code == 1 and "frontmatter" in " ".join(out["failed"][0]["issues"])


def test_check_notes_changed_picks_up_new_and_modified_notes_only(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    (tmp_path / "new note.md").write_text(GOOD, encoding="utf-8")
    (tmp_path / "skip.txt").write_text("x", encoding="utf-8")
    sys.path.insert(0, str(SCRIPTS))
    try:
        from check_notes import changed_notes
    finally:
        sys.path.remove(str(SCRIPTS))
    assert changed_notes(tmp_path) == ["new note.md"]
