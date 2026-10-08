import io
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from helpers import FailingConverter, make_config
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import ValidationError
from typer.testing import CliRunner

from docling_pipeline import cli
from docling_pipeline.config import ObservabilityConfig, TelemetryExporter
from docling_pipeline.observability import (
    CONSOLE_FORMAT,
    Telemetry,
    TraceContextFormatter,
    build_log_exporter,
    build_providers,
    build_resource,
    build_span_exporter,
    setup_telemetry,
)
from docling_pipeline.pipeline import DocumentPipeline

STAGES = {"document.convert", "document.export", "document.chunk"}


def by_name(spans, name):
    return [s for s in spans if s.name == name]


def one(spans, name):
    [span] = by_name(spans, name)
    return span


def doc_span(spans, doc_name):
    return next(
        s for s in by_name(spans, "document.process") if s.attributes["doc.name"] == doc_name
    )


def children(spans, parent):
    return [s for s in spans if s.parent and s.parent.span_id == parent.context.span_id]


def hex_trace(span):
    return trace.format_trace_id(span.context.trace_id)


def hex_span(span):
    return trace.format_span_id(span.context.span_id)


# --- FR-011: span hierarchy ---------------------------------------------------------------


@pytest.mark.spec("FR-011", "NFR-005")
def test_span_tree_for_successful_run(corpus: Path, tmp_path: Path, spans):
    cfg = make_config([corpus / "report.html", corpus / "notes.md"], tmp_path / "out")
    DocumentPipeline(cfg).run()
    finished = spans.get_finished_spans()

    run = one(finished, "pipeline.run")
    assert run.parent is None
    assert len({s.context.trace_id for s in finished}) == 1  # exactly one trace
    assert {s.name for s in children(finished, run)} == {"pipeline.discover", "document.process"}

    assert run.attributes["pipeline.exports"] == ("markdown", "json")
    assert run.attributes["pipeline.chunker"] == "hierarchical"
    assert run.attributes["pipeline.documents.total"] == 2
    assert run.attributes["pipeline.documents.succeeded"] == 2
    assert run.attributes["pipeline.documents.failed"] == 0
    assert one(finished, "pipeline.discover").attributes["discover.sources"] == 2

    report = doc_span(finished, "report")
    assert report.attributes["doc.status"] == "success"
    assert report.attributes["doc.is_url"] is False
    assert report.attributes["doc.chunks"] > 0
    stages = {s.name: s for s in children(finished, report)}
    assert set(stages) == STAGES
    assert stages["document.convert"].attributes["docling.status"] == "success"
    assert stages["document.export"].attributes["export.formats"] == ("markdown", "json")
    assert stages["document.chunk"].attributes["chunks.count"] == report.attributes["doc.chunks"]
    assert all(s.status.status_code is not StatusCode.ERROR for s in finished)


@pytest.mark.spec("FR-011")
def test_failed_document_span_is_error_and_siblings_are_not(corpus: Path, tmp_path: Path, spans):
    converter = FailingConverter(fail_on="notes.md")
    DocumentPipeline(make_config([corpus], tmp_path / "out"), converter=converter).run()
    finished = spans.get_finished_spans()

    failed = doc_span(finished, "notes")
    assert failed.status.status_code is StatusCode.ERROR
    assert failed.attributes["doc.status"] == "failure"
    assert any(e.name == "exception" for e in failed.events)
    convert = one(children(finished, failed), "document.convert")
    assert convert.status.status_code is StatusCode.ERROR

    for name in ("report", "deep"):
        assert doc_span(finished, name).status.status_code is not StatusCode.ERROR
    assert one(finished, "pipeline.run").attributes["pipeline.documents.failed"] == 1


@pytest.mark.spec("FR-011")
def test_skipped_document_has_no_stage_spans(corpus: Path, tmp_path: Path, spans):
    cfg = make_config([corpus / "notes.md"], tmp_path / "out", skip_existing=True)
    DocumentPipeline(cfg).run()
    spans.clear()
    DocumentPipeline(cfg).run()
    finished = spans.get_finished_spans()

    skipped = doc_span(finished, "notes")
    assert skipped.attributes["doc.status"] == "skipped"
    assert any(e.name == "skipped" for e in skipped.events)
    assert children(finished, skipped) == []


@pytest.mark.spec("FR-011")
def test_no_chunk_span_when_chunking_disabled(corpus: Path, tmp_path: Path, spans):
    cfg = make_config([corpus / "notes.md"], tmp_path / "out")
    cfg.chunking.enabled = False
    DocumentPipeline(cfg).run()
    finished = spans.get_finished_spans()
    names = {s.name for s in children(finished, doc_span(finished, "notes"))}
    assert names == {"document.convert", "document.export"}
    assert one(finished, "pipeline.run").attributes["pipeline.chunker"] == "none"


# --- FR-012: logs correlated with traces ---------------------------------------------------


def _bodies(logs):
    return [r.log_record for r in logs.get_finished_logs()]


@pytest.mark.spec("FR-012", "NFR-005")
def test_document_logs_carry_span_context_and_attributes(corpus, tmp_path, spans, logs):
    DocumentPipeline(make_config([corpus / "report.html"], tmp_path / "out")).run()
    finished = spans.get_finished_spans()
    records = _bodies(logs)

    [processed] = [r for r in records if str(r.body).startswith("document processed")]
    report = doc_span(finished, "report")
    assert processed.trace_id == report.context.trace_id
    assert processed.span_id == report.context.span_id
    assert processed.severity_text == "INFO"
    assert processed.attributes["doc.name"] == "report"
    assert processed.attributes["doc.status"] == "success"

    run = one(finished, "pipeline.run")
    for prefix in ("pipeline run started", "pipeline run finished"):
        [rec] = [r for r in records if str(r.body).startswith(prefix)]
        assert rec.span_id == run.context.span_id


@pytest.mark.spec("FR-012")
def test_failure_logged_at_error_with_exception(corpus, tmp_path, logs):
    converter = FailingConverter(fail_on="notes.md")
    DocumentPipeline(
        make_config([corpus / "notes.md"], tmp_path / "out"), converter=converter
    ).run()
    [failed] = [r for r in _bodies(logs) if str(r.body).startswith("document failed")]
    assert failed.severity_text == "ERROR"
    assert failed.attributes["doc.status"] == "failure"
    assert failed.attributes["exception.type"] == "RuntimeError"
    assert "simulated parser crash" in failed.attributes["exception.stacktrace"]


@pytest.mark.spec("FR-012")
def test_console_log_line_includes_trace_and_span_ids():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TraceContextFormatter(CONSOLE_FORMAT))
    logger = logging.getLogger("test.console")
    logger.addHandler(handler)
    try:
        with trace.get_tracer("t").start_as_current_span("s") as span:
            logger.warning("hello")
        logger.warning("outside")
    finally:
        logger.removeHandler(handler)

    inside, outside = stream.getvalue().splitlines()
    assert inside == f"hello [trace_id={hex_trace(span)} span_id={hex_span(span)}]"
    assert re.fullmatch(r"outside \[trace_id=0{32} span_id=0{16}\]", outside)


# --- FR-013: correlation IDs in outputs ----------------------------------------------------


@pytest.mark.spec("FR-013")
def test_manifest_and_meta_carry_trace_ids(corpus: Path, tmp_path: Path, spans):
    out = tmp_path / "out"
    DocumentPipeline(make_config([corpus / "report.html"], out)).run()
    finished = spans.get_finished_spans()

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["trace_id"] == hex_trace(one(finished, "pipeline.run"))
    meta = json.loads((out / "report" / "meta.json").read_text())
    report = doc_span(finished, "report")
    assert (meta["trace_id"], meta["span_id"]) == (hex_trace(report), hex_span(report))


@pytest.mark.spec("FR-013")
def test_cli_prints_trace_id(corpus: Path, tmp_path: Path, spans):
    result = CliRunner().invoke(
        cli.app,
        ["run", str(corpus / "notes.md"), "-o", str(tmp_path / "out"), "--chunker", "hierarchical"],
    )
    assert result.exit_code == 0, result.output
    run = one(spans.get_finished_spans(), "pipeline.run")
    assert f"trace_id: {hex_trace(run)}" in result.output


# --- FR-014: configuration -----------------------------------------------------------------


@pytest.mark.spec("FR-014")
def test_exporter_selection_and_otlp_endpoint():
    cfg = ObservabilityConfig(traces_exporter="console", logs_exporter="console")
    assert isinstance(build_span_exporter(cfg), ConsoleSpanExporter)
    assert isinstance(build_log_exporter(cfg), ConsoleLogRecordExporter)

    cfg = ObservabilityConfig(
        traces_exporter="otlp", logs_exporter="otlp", otlp_endpoint="http://collector:4318/"
    )
    span_exp, log_exp = build_span_exporter(cfg), build_log_exporter(cfg)
    assert isinstance(span_exp, OTLPSpanExporter)
    assert isinstance(log_exp, OTLPLogExporter)
    assert span_exp._endpoint == "http://collector:4318/v1/traces"
    assert log_exp._endpoint == "http://collector:4318/v1/logs"

    none = ObservabilityConfig(traces_exporter="none", logs_exporter="none")
    assert build_span_exporter(none) is None
    assert build_log_exporter(none) is None


@pytest.mark.spec("FR-014")
def test_exporters_default_from_standard_env_vars(monkeypatch):
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")
    monkeypatch.setenv("OTEL_LOGS_EXPORTER", "console")
    cfg = ObservabilityConfig()
    assert cfg.traces_exporter is TelemetryExporter.OTLP
    assert cfg.logs_exporter is TelemetryExporter.CONSOLE
    monkeypatch.delenv("OTEL_TRACES_EXPORTER")
    assert ObservabilityConfig().traces_exporter is TelemetryExporter.NONE


@pytest.mark.spec("FR-014")
def test_resource_attributes():
    attrs = build_resource(ObservabilityConfig(service_name="svc", environment="prod")).attributes
    assert attrs["service.name"] == "svc"
    assert attrs["service.version"] == "0.1.0"
    assert attrs["deployment.environment.name"] == "prod"


@pytest.mark.spec("FR-014")
@pytest.mark.parametrize(
    "kwargs",
    [{"traces_exporter": "jaeger"}, {"sample_ratio": 1.5}, {"sample_ratio": -0.1}],
)
def test_invalid_observability_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        ObservabilityConfig(**kwargs)


@pytest.mark.spec("FR-014")
def test_sample_ratio_zero_records_nothing():
    exporter = InMemorySpanExporter()
    tp, _, _ = build_providers(
        ObservabilityConfig(sample_ratio=0.0), span_exporter=exporter, batch=False
    )
    with tp.get_tracer("t").start_as_current_span("s") as span:
        assert not span.is_recording()
    assert exporter.get_finished_spans() == ()


@pytest.mark.spec("FR-014")
def test_disabled_installs_no_otel_handler():
    root = logging.getLogger()
    before = list(root.handlers)
    tel = setup_telemetry(ObservabilityConfig(enabled=False), console_level=logging.INFO)
    try:
        assert tel.tracer_provider is None
        assert not any(isinstance(h, LoggingHandler) for h in tel.handlers)
        assert len(tel.handlers) == 1  # console only
    finally:
        tel.shutdown()
    assert root.handlers == before


@pytest.mark.spec("FR-014", "FR-019")
def test_cli_telemetry_flags_set_config(corpus: Path, tmp_path: Path, monkeypatch):
    seen = {}

    def fake_setup(cfg, **kwargs):
        seen["cfg"] = cfg
        return Telemetry()

    monkeypatch.setattr(cli, "setup_telemetry", fake_setup)
    result = CliRunner().invoke(
        cli.app,
        [
            "run", str(corpus / "notes.md"), "-o", str(tmp_path / "out"),
            "--chunker", "hierarchical",
            "--telemetry", "otlp", "--otlp-endpoint", "http://collector:4318",
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    cfg = seen["cfg"]
    assert (
        cfg.traces_exporter is cfg.logs_exporter is cfg.metrics_exporter is TelemetryExporter.OTLP
    )
    assert cfg.otlp_endpoint == "http://collector:4318"


# --- FR-015: lifecycle ---------------------------------------------------------------------


@pytest.mark.spec("FR-015")
def test_setup_reuses_existing_providers_and_shutdown_only_flushes(_telemetry):
    root = logging.getLogger()
    before = list(root.handlers)
    tel = setup_telemetry(ObservabilityConfig(), console_level=logging.INFO)
    assert tel.owns_providers is False
    assert tel.tracer_provider is _telemetry.tracer_provider
    tel.shutdown()
    assert root.handlers == before
    # Shared providers still work after a non-owning shutdown.
    with trace.get_tracer("t").start_as_current_span("still-alive") as span:
        assert span.is_recording()


@pytest.mark.spec("FR-015")
def test_owned_providers_are_shut_down():
    exporter = InMemorySpanExporter()
    tp, lp, mp = build_providers(ObservabilityConfig(), span_exporter=exporter, batch=True)
    tp.get_tracer("t").start_span("pending").end()  # sits in the batch queue
    Telemetry(
        tracer_provider=tp, logger_provider=lp, meter_provider=mp, owns_providers=True
    ).shutdown()
    assert [s.name for s in exporter.get_finished_spans()] == ["pending"]  # flushed
    assert exporter._stopped


@pytest.mark.spec("FR-015")
@pytest.mark.parametrize("failure", ["document", "exception"])
def test_cli_shuts_down_telemetry_on_failure(tmp_path: Path, monkeypatch, failure):
    calls = []

    class Recorder(Telemetry):
        def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(cli, "setup_telemetry", lambda cfg, **kw: Recorder())
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf")
    if failure == "exception":

        def boom(self, on_result=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(cli.DocumentPipeline, "run", boom)

    result = CliRunner().invoke(
        cli.app, ["run", str(bad), "-o", str(tmp_path / "out"), "--no-chunk", "--no-ocr"]
    )
    assert result.exit_code == 1
    assert calls == ["shutdown"]


# --- NFR-004: telemetry never breaks the pipeline -----------------------------------------


@pytest.mark.spec("NFR-004")
def test_unreachable_collector_does_not_affect_results(corpus: Path, tmp_path: Path):
    """Runs the real CLI in a fresh process so it installs (and owns) OTLP exporters."""
    config = tmp_path / "c.yaml"
    config.write_text("observability:\n  otlp_timeout_s: 2\n")
    out = tmp_path / "out"
    start = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable, "-m", "docling_pipeline.cli", "run", str(corpus / "notes.md"),
            "-c", str(config), "-o", str(out), "--chunker", "hierarchical",
            "--telemetry", "otlp", "--otlp-endpoint", "http://127.0.0.1:9",  # nothing listens
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )  # fmt: skip
    elapsed = time.monotonic() - start

    assert proc.returncode == 0, proc.stdout + proc.stderr
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["counts"] == {"success": 1}
    assert (out / "notes" / "chunks.jsonl").exists()
    assert elapsed < 60, f"shutdown blocked for {elapsed:.0f}s"
