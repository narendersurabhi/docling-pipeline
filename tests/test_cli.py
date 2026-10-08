import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from docling_pipeline.cli import app

runner = CliRunner()


@pytest.mark.spec("FR-010")
def test_run_with_flags_overriding_config(corpus: Path, tmp_path: Path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("input_paths: [does/not/exist]\nexports: [json]\n")
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "run",
            str(corpus / "notes.md"),
            "--config",
            str(cfg),
            "--output",
            str(out),
            "--format",
            "markdown",
            "--chunker",
            "hierarchical",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "success" in result.output
    assert (out / "notes" / "document.md").exists()
    assert not (out / "notes" / "document.json").exists()  # --format replaced config exports
    assert json.loads((out / "manifest.json").read_text())["counts"] == {"success": 1}


@pytest.mark.spec("FR-010")
def test_exit_code_1_when_a_document_fails(tmp_path: Path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"this is not a pdf")
    result = runner.invoke(
        app, ["run", str(bad), "--output", str(tmp_path / "out"), "--no-chunk", "--no-ocr"]
    )
    assert result.exit_code == 1, result.output
    assert "failure" in result.output


@pytest.mark.spec("FR-010")
def test_no_inputs_is_usage_error(tmp_path: Path):
    result = runner.invoke(app, ["run", "--output", str(tmp_path / "out")])
    assert result.exit_code == 2
