"""Conversion checks; real rendering requires LibreOffice acceptance testing."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import document_to_pdf as converter  # noqa: E402


@pytest.fixture
def document(tmp_path, monkeypatch):
    monkeypatch.setattr(converter.tempfile, "tempdir", str(tmp_path))
    source = tmp_path / "vault" / "Attachments" / "A report with spaces.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original document")
    monkeypatch.chdir(source.parent)
    return source


def _converter(monkeypatch, *, failure=None):
    def run(command, **kwargs):
        if failure == "exit":
            raise subprocess.CalledProcessError(1, command)
        if failure != "no-output":
            staged = Path(command[-1])
            staged.write_bytes(b"modified by converter")  # Only the private copy may change.
            output = Path(command[command.index("--outdir") + 1])
            (output / staged.with_suffix(".pdf").name).write_bytes(b"%PDF-1.7\nfixture")
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(converter.subprocess, "run", run)


@pytest.mark.parametrize("extension", [".docx", ".DOC", ".odt"])
@pytest.mark.parametrize("input_path", ["relative", "absolute"])
def test_cli_keeps_original_provenance_and_source_bytes(
    document, monkeypatch, capsys, extension, input_path,
):
    source = document.rename(document.with_suffix(extension))
    _converter(monkeypatch)
    argument = source.name if input_path == "relative" else source
    monkeypatch.setattr(sys, "argv", [
        "document_to_pdf.py", str(argument), "--soffice", "soffice",
    ])
    assert converter.main() == 0
    pdf = Path(capsys.readouterr().out.strip())
    assert pdf.name == source.with_suffix(".pdf").name
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert pdf.parent != source.parent
    assert source.read_bytes() == b"original document"


def test_a_stalled_converter_times_out_instead_of_hanging(document, monkeypatch, capsys):
    seen = {}

    def run(command, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(command, kwargs.get("timeout"))

    monkeypatch.setattr(converter.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["document_to_pdf.py", str(document), "--soffice", "soffice"])
    assert converter.main() == 1
    assert seen.get("timeout") == converter.CONVERT_TIMEOUT
    assert "timed out" in capsys.readouterr().err
    assert document.read_bytes() == b"original document"


@pytest.mark.parametrize("failure", ["exit", "no-output"])
def test_failed_conversion_cannot_reuse_previous_pdf(document, tmp_path, monkeypatch, failure):
    _converter(monkeypatch)
    earlier = converter.convert_document(document, "soffice")
    _converter(monkeypatch, failure=failure)
    with pytest.raises((subprocess.CalledProcessError, FileNotFoundError)):
        converter.convert_document(document, "soffice")
    assert earlier.read_bytes().startswith(b"%PDF-")
    assert document.read_bytes() == b"original document"
    assert not list(tmp_path.glob("obsidian-convert-*"))
