from pathlib import Path
from types import SimpleNamespace

import pytest
from docling.datamodel.base_models import ConversionStatus
from helpers import FailingConverter, make_config
from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    MetricExportResult,
)
from pydantic import ValidationError

from docling_pipeline.config import ChunkerType, ChunkingConfig, ObservabilityConfig
from docling_pipeline.observability import (
    METRIC_ATTRIBUTE_KEYS,
    SECONDS_BUCKETS,
    Telemetry,
    build_metric_exporter,
    build_providers,
    setup_telemetry,
)
from docling_pipeline.pipeline import DocumentPipeline, doc_format
from docling_pipeline.sources import Source


def points(metrics_by_name, name, **attrs):
    """Data points of `name` whose attributes include `attrs` (dots spelled as __)."""
    want = {k.replace("__", "."): v for k, v in attrs.items()}
    metric = metrics_by_name.get(name)
    if metric is None:
        return []
    return [p for p in metric.data.data_points if want.items() <= dict(p.attributes).items()]


def total(metrics_by_name, name, **attrs):
    return sum(getattr(p, "value", None) or p.count for p in points(metrics_by_name, name, **attrs))


class FailedResultConverter:
    """Docling reporting FAILURE without raising."""

    def convert(self, source, **kwargs):
        return SimpleNamespace(
            status=ConversionStatus.FAILURE,
            errors=[SimpleNamespace(error_message="unreadable")],
        )


# --- FR-016: instruments -------------------------------------------------------------------


@pytest.mark.spec("FR-016")
def test_instruments_for_successful_run(corpus: Path, tmp_path: Path, collect_metrics):
    cfg = make_config([corpus / "report.html", corpus / "notes.md"], tmp_path / "out")
    summary = DocumentPipeline(cfg).run()
    m = collect_metrics()

    assert total(m, "pipeline.runs", outcome="completed") == 1
    assert total(m, "pipeline.run.duration", outcome="completed") == 1
    for fmt in ("html", "md"):
        assert total(m, "pipeline.documents", doc__status="success", doc__format=fmt) == 1
        assert total(m, "pipeline.document.duration", doc__format=fmt) == 1
        for stage in ("convert", "export", "chunk"):
            assert (
                total(m, "pipeline.stage.duration", stage=stage, outcome="ok", doc__format=fmt) == 1
            )
    assert total(m, "pipeline.chunks", chunker__type="hierarchical") == sum(
        r.num_chunks for r in summary.results
    )
    assert "pipeline.errors" not in m
    assert "pipeline.chunk.tokens" not in m  # hierarchical chunker has no tokenizer

    units = {name: metric.unit for name, metric in m.items()}
    assert units["pipeline.runs"] == "{run}"
    assert units["pipeline.document.duration"] == "s"
    assert units["pipeline.pages"] == "{page}"
    [point] = points(m, "pipeline.document.duration", doc__format="html")
    assert list(point.explicit_bounds) == SECONDS_BUCKETS


@pytest.mark.spec("FR-016")
def test_exception_failure_counts_error_by_stage_and_type(corpus, tmp_path, collect_metrics):
    converter = FailingConverter(fail_on="notes.md")
    DocumentPipeline(
        make_config([corpus / "notes.md"], tmp_path / "out"), converter=converter
    ).run()
    m = collect_metrics()

    assert total(m, "pipeline.errors", stage="convert", error__type="RuntimeError") == 1
    assert total(m, "pipeline.documents", doc__status="failure", doc__format="md") == 1
    assert total(m, "pipeline.stage.duration", stage="convert", outcome="error") == 1
    assert "pipeline.pages" not in m


@pytest.mark.spec("FR-016")
def test_reported_failure_counts_conversion_failed(corpus, tmp_path, collect_metrics):
    cfg = make_config([corpus / "notes.md"], tmp_path / "out")
    DocumentPipeline(cfg, converter=FailedResultConverter()).run()
    m = collect_metrics()
    assert total(m, "pipeline.errors", stage="convert", error__type="ConversionFailed") == 1
    assert total(m, "pipeline.stage.duration", stage="convert", outcome="error") == 1


@pytest.mark.spec("FR-016")
def test_skipped_documents_counted_without_duration(corpus, tmp_path, collect_metrics):
    cfg = make_config([corpus / "notes.md"], tmp_path / "out", skip_existing=True)
    DocumentPipeline(cfg).run()
    collect_metrics()  # discard first run
    DocumentPipeline(cfg).run()
    m = collect_metrics()
    assert total(m, "pipeline.documents", doc__status="skipped", doc__format="md") == 1
    assert "pipeline.document.duration" not in m
    assert "pipeline.stage.duration" not in m


@pytest.mark.spec("FR-016")
def test_aborted_run_outcome(corpus, tmp_path, collect_metrics):
    cfg = make_config([corpus / "notes.md"], tmp_path / "out", raise_on_error=True)
    with pytest.raises(RuntimeError):
        DocumentPipeline(cfg, converter=FailingConverter(fail_on="notes")).run()
    m = collect_metrics()
    assert total(m, "pipeline.runs", outcome="aborted") == 1
    assert total(m, "pipeline.run.duration", outcome="aborted") == 1


@pytest.mark.spec("FR-016")
@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("/data/Report.PDF", "pdf"),
        ("https://arxiv.org/pdf/2408.09869", "unknown"),
        ("https://example.com/files/deck.pptx?download=1", "pptx"),
        ("/data/README", "unknown"),
    ],
)
def test_doc_format_label(location, expected):
    assert doc_format(Source(location=location, name="x")) == expected


@pytest.mark.slow
@pytest.mark.spec("FR-016")
def test_chunk_token_histogram_with_hybrid_chunker(corpus, tmp_path, collect_metrics):
    cfg = make_config([corpus / "report.html"], tmp_path / "out")
    cfg.chunking = ChunkingConfig(chunker=ChunkerType.HYBRID, max_tokens=64)
    [result] = DocumentPipeline(cfg).run().results
    m = collect_metrics()
    [point] = points(m, "pipeline.chunk.tokens", chunker__type="hybrid")
    assert point.count == result.num_chunks
    assert point.max <= 64


# --- FR-017: bounded cardinality -----------------------------------------------------------


@pytest.mark.spec("FR-017")
def test_metric_attributes_are_bounded(corpus, tmp_path, collect_metrics):
    out = tmp_path / "out"
    cfg = make_config([corpus], out, skip_existing=True)
    DocumentPipeline(cfg, converter=FailingConverter(fail_on="notes.md")).run()
    DocumentPipeline(cfg).run()  # includes skipped docs
    m = collect_metrics()

    forbidden_values = {"report", "notes", "deep", str(corpus), str(out)}
    seen_keys = set()
    for metric in m.values():
        for p in metric.data.data_points:
            seen_keys |= set(p.attributes)
            assert not forbidden_values & {str(v) for v in p.attributes.values()}
            assert not any("/" in str(v) for v in p.attributes.values())
    assert seen_keys <= METRIC_ATTRIBUTE_KEYS
    assert {"doc.status", "doc.format", "stage", "outcome", "error.type"} <= seen_keys


# --- FR-018: exemplars ---------------------------------------------------------------------


@pytest.mark.spec("FR-018")
def test_duration_exemplars_point_at_spans(corpus, tmp_path, spans, collect_metrics):
    DocumentPipeline(make_config([corpus / "report.html"], tmp_path / "out")).run()
    m = collect_metrics()
    finished = spans.get_finished_spans()
    span_ids = {s.name: s.context.span_id for s in finished}
    trace_id = finished[0].context.trace_id

    [doc_point] = points(m, "pipeline.document.duration", doc__format="html")
    assert doc_point.exemplars
    for ex in doc_point.exemplars:
        assert (ex.trace_id, ex.span_id) == (trace_id, span_ids["document.process"])

    for stage in ("convert", "export", "chunk"):
        [stage_point] = points(m, "pipeline.stage.duration", stage=stage)
        assert {ex.span_id for ex in stage_point.exemplars} == {span_ids[f"document.{stage}"]}


# --- FR-019: configuration and lifecycle ---------------------------------------------------


class CollectingMetricExporter(MetricExporter):
    def __init__(self):
        super().__init__()
        self.batches = []

    def export(self, metrics_data, timeout_millis=10_000, **kwargs):
        self.batches.append(metrics_data)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis=10_000):
        return True

    def shutdown(self, timeout_millis=30_000, **kwargs):
        pass


@pytest.mark.spec("FR-019")
def test_metric_exporter_selection(monkeypatch):
    assert isinstance(
        build_metric_exporter(ObservabilityConfig(metrics_exporter="console")),
        ConsoleMetricExporter,
    )
    otlp = build_metric_exporter(
        ObservabilityConfig(metrics_exporter="otlp", otlp_endpoint="http://collector:4318")
    )
    assert isinstance(otlp, OTLPMetricExporter)
    assert otlp._endpoint == "http://collector:4318/v1/metrics"
    assert build_metric_exporter(ObservabilityConfig(metrics_exporter="none")) is None

    monkeypatch.setenv("OTEL_METRICS_EXPORTER", "otlp")
    assert ObservabilityConfig().metrics_exporter == "otlp"
    with pytest.raises(ValidationError):
        ObservabilityConfig(metric_export_interval_s=0)


@pytest.mark.spec("FR-019")
def test_short_run_metrics_exported_on_shutdown(monkeypatch):
    exporter = CollectingMetricExporter()
    monkeypatch.setattr(
        "docling_pipeline.observability.build_metric_exporter", lambda cfg: exporter
    )
    cfg = ObservabilityConfig(metric_export_interval_s=3600)  # far longer than the "run"
    tp, lp, mp = build_providers(cfg, batch=False)
    mp.get_meter("t").create_counter("short.run").add(3)
    assert exporter.batches == []

    Telemetry(
        tracer_provider=tp, logger_provider=lp, meter_provider=mp, owns_providers=True
    ).shutdown()

    names = {
        metric.name
        for batch in exporter.batches
        for rm in batch.resource_metrics
        for sm in rm.scope_metrics
        for metric in sm.metrics
    }
    assert "short.run" in names


@pytest.mark.spec("FR-019")
def test_setup_reuses_meter_provider_and_disabled_has_none(_telemetry):
    tel = setup_telemetry(ObservabilityConfig(), console_level=None)
    assert tel.meter_provider is metrics.get_meter_provider() is _telemetry.meter_provider
    tel.shutdown()

    off = setup_telemetry(ObservabilityConfig(enabled=False), console_level=None)
    assert off.meter_provider is None
    off.shutdown()
