import json
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from helpers import FailingConverter, make_config

from docling_pipeline.config import (
    ChunkerType,
    ChunkingConfig,
    ExportFormat,
)
from docling_pipeline.pipeline import DocumentPipeline

CHUNK_FIELDS = {
    "id",
    "source",
    "chunk_index",
    "text",
    "contextualized_text",
    "headings",
    "pages",
    "doc_item_refs",
    "labels",
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.spec("FR-004", "NFR-002")
def test_all_export_formats_written(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    cfg = make_config([corpus / "report.html"], out, exports=list(ExportFormat))
    [result] = DocumentPipeline(cfg).run().results

    assert result.status == "success"
    doc_dir = out / "report"
    for ext in ("md", "json", "html", "txt", "doctags"):
        assert (doc_dir / f"document.{ext}").stat().st_size > 0
    assert "# Quarterly Report" in (doc_dir / "document.md").read_text()
    assert "| EMEA" in (doc_dir / "document.md").read_text()  # table preserved


@pytest.mark.spec("FR-004")
def test_json_export_round_trips_to_docling_document(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    DocumentPipeline(make_config([corpus / "report.html"], out)).run()
    data = json.loads((out / "report" / "document.json").read_text())
    doc = DoclingDocument.model_validate(data)
    assert len(doc.tables) == 1


@pytest.mark.spec("FR-005", "NFR-002")
def test_chunks_jsonl_schema(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    [result] = DocumentPipeline(make_config([corpus / "report.html"], out)).run().results

    chunks = read_jsonl(out / "report" / "chunks.jsonl")
    assert result.num_chunks == len(chunks) > 0
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert c.keys() >= CHUNK_FIELDS
        assert c["id"] == f"report:{c['chunk_index']}"
        assert c["source"] == str((corpus / "report.html").resolve())
        assert c["pages"] == []  # HTML is not paginated
        assert "num_tokens" not in c  # hierarchical chunker has no tokenizer

    revenue = next(c for c in chunks if "Revenue grew" in c["text"])
    assert revenue["headings"][-1] == "Revenue"
    assert revenue["contextualized_text"].startswith("Quarterly Report\nRevenue")


@pytest.mark.spec("FR-005")
def test_chunking_disabled_writes_no_chunks(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    cfg = make_config([corpus / "notes.md"], out)
    cfg.chunking.enabled = False
    [result] = DocumentPipeline(cfg).run().results
    assert result.num_chunks == 0
    assert not (out / "notes" / "chunks.jsonl").exists()


@pytest.mark.slow
@pytest.mark.spec("FR-005")
def test_hybrid_chunker_respects_max_tokens(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    cfg = make_config([corpus / "report.html"], out)
    cfg.chunking = ChunkingConfig(chunker=ChunkerType.HYBRID, max_tokens=64)
    DocumentPipeline(cfg).run()
    chunks = read_jsonl(out / "report" / "chunks.jsonl")
    assert all(c["num_tokens"] <= 64 for c in chunks)


@pytest.mark.spec("FR-006")
def test_one_failure_does_not_stop_batch(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    converter = FailingConverter(fail_on="notes.md")
    summary = DocumentPipeline(make_config([corpus], out), converter=converter).run()

    by_name = {r.name: r for r in summary.results}
    assert by_name["notes"].status == "failure"
    assert "simulated parser crash" in by_name["notes"].errors[0]
    assert by_name["report"].status == "success"
    assert by_name["deep"].status == "success"


@pytest.mark.spec("FR-006")
def test_raise_on_error_stops_batch(corpus: Path, tmp_path: Path):
    cfg = make_config([corpus], tmp_path / "out", raise_on_error=True)
    converter = FailingConverter(fail_on="deep.md")  # first in sorted order
    with pytest.raises(RuntimeError, match="simulated"):
        DocumentPipeline(cfg, converter=converter).run()
    assert len(converter.calls) == 1


@pytest.mark.spec("FR-007")
def test_meta_and_manifest(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    converter = FailingConverter(fail_on="notes.md")
    DocumentPipeline(make_config([corpus], out), converter=converter).run()

    meta = json.loads((out / "report" / "meta.json").read_text())
    assert meta.keys() == {
        "source",
        "name",
        "status",
        "output_dir",
        "files",
        "num_pages",
        "num_chunks",
        "seconds",
        "errors",
        "trace_id",
        "span_id",
    }
    assert meta["status"] == "success"
    assert set(meta["files"]) == {"markdown", "json", "chunks"}

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["counts"] == {"success": 2, "failure": 1}
    assert len(manifest["documents"]) == 3
    assert manifest["started_at"].endswith("+00:00")
    assert manifest["finished_at"] >= manifest["started_at"]


@pytest.mark.spec("FR-008")
def test_skip_existing_skips_successes_and_retries_failures(corpus: Path, tmp_path: Path):
    out = tmp_path / "out"
    cfg = make_config([corpus], out, skip_existing=True)

    first = DocumentPipeline(cfg, converter=FailingConverter(fail_on="notes.md")).run()
    assert {r.name: r.status for r in first.results}["notes"] == "failure"

    retry = FailingConverter(fail_on="never-matches")
    second = DocumentPipeline(cfg, converter=retry).run()
    statuses = {r.name: r.status for r in second.results}

    assert statuses == {"deep": "skipped", "notes": "success", "report": "skipped"}
    assert [Path(c).name for c in retry.calls] == ["notes.md"]
