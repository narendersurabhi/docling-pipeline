import shutil
from pathlib import Path

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from docling_pipeline.config import ObservabilityConfig
from docling_pipeline.observability import setup_telemetry

FIXTURES = Path(__file__).parent / "fixtures"

# OpenTelemetry global providers can only be installed once per process, so the whole
# session shares in-memory exporters (NFR-005). Each test starts with them empty.
SPANS = InMemorySpanExporter()
LOGS = InMemoryLogRecordExporter()


@pytest.fixture(scope="session", autouse=True)
def _telemetry():
    tel = setup_telemetry(
        ObservabilityConfig(),
        console_level=None,
        span_exporter=SPANS,
        log_exporter=LOGS,
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
def corpus(tmp_path: Path) -> Path:
    """A small input tree: two supported docs, one nested doc, one unsupported file."""
    root = tmp_path / "input"
    (root / "nested").mkdir(parents=True)
    shutil.copy(FIXTURES / "report.html", root / "report.html")
    shutil.copy(FIXTURES / "notes.md", root / "notes.md")
    shutil.copy(FIXTURES / "notes.md", root / "nested" / "deep.md")
    (root / "malware.exe").write_bytes(b"MZ")
    return root
