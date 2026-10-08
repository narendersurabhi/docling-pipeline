import shutil
from pathlib import Path

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics import Counter, Histogram
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from docling_pipeline.config import ObservabilityConfig
from docling_pipeline.observability import setup_telemetry

FIXTURES = Path(__file__).parent / "fixtures"

# OpenTelemetry global providers can only be installed once per process, so the whole
# session shares in-memory exporters (NFR-005). Each test starts with them empty.
SPANS = InMemorySpanExporter()
LOGS = InMemoryLogRecordExporter()
# Delta temporality: each collection returns only what was recorded since the previous one.
METRICS = InMemoryMetricReader(
    preferred_temporality={
        Counter: AggregationTemporality.DELTA,
        Histogram: AggregationTemporality.DELTA,
    }
)


@pytest.fixture(scope="session", autouse=True)
def _telemetry():
    tel = setup_telemetry(
        ObservabilityConfig(),
        console_level=None,
        span_exporter=SPANS,
        log_exporter=LOGS,
        metric_reader=METRICS,
        batch=False,
    )
    yield tel
    tel.shutdown()


@pytest.fixture
def spans() -> InMemorySpanExporter:
    SPANS.clear()
    return SPANS


@pytest.fixture
def logs() -> InMemoryLogRecordExporter:
    LOGS.clear()
    return LOGS


@pytest.fixture
def collect_metrics():
    """Returns a function giving {metric name: Metric} recorded since the last call
    (or since the fixture was requested)."""
    METRICS.get_metrics_data()  # drain anything recorded by earlier tests

    def collect() -> dict:
        data = METRICS.get_metrics_data()
        found: dict = {}
        for rm in data.resource_metrics if data else []:
            for sm in rm.scope_metrics:
                for metric in sm.metrics:
                    found[metric.name] = metric
        return found

    return collect


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A small input tree: two supported docs, one nested doc, one unsupported file."""
    root = tmp_path / "input"
    (root / "nested").mkdir(parents=True)
    shutil.copy(FIXTURES / "report.html", root / "report.html")
    shutil.copy(FIXTURES / "notes.md", root / "notes.md")
    shutil.copy(FIXTURES / "notes.md", root / "nested" / "deep.md")
    (root / "malware.exe").write_bytes(b"MZ")
    return root
