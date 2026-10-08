"""Pipeline configuration, loadable from YAML and overridable from the CLI."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ExportFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    TEXT = "text"
    DOCTAGS = "doctags"


class ChunkerType(StrEnum):
    HYBRID = "hybrid"
    HIERARCHICAL = "hierarchical"


class ConversionConfig(BaseModel):
    do_ocr: bool = True
    do_table_structure: bool = True
    table_mode: str = Field("accurate", pattern="^(accurate|fast)$")
    generate_picture_images: bool = False
    images_scale: float = 2.0
    num_threads: int = 4
    device: str = Field("auto", pattern="^(auto|cpu|mps|xpu|cuda(:[0-9]+)?)$")
    document_timeout: float | None = None
    max_num_pages: int | None = None
    max_file_size_mb: float | None = None


class ChunkingConfig(BaseModel):
    enabled: bool = True
    chunker: ChunkerType = ChunkerType.HYBRID
    tokenizer: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_tokens: int = 512
    merge_peers: bool = True


class TelemetryExporter(StrEnum):
    NONE = "none"
    CONSOLE = "console"
    OTLP = "otlp"


def _exporter_from_env(var: str) -> TelemetryExporter:
    value = os.environ.get(var, "none").strip().lower()
    return (
        TelemetryExporter(value)
        if value in TelemetryExporter._value2member_map_
        else (TelemetryExporter.NONE)
    )


class ObservabilityConfig(BaseModel):
    enabled: bool = True
    service_name: str = "docling-pipeline"
    environment: str = "dev"
    traces_exporter: TelemetryExporter = Field(
        default_factory=lambda: _exporter_from_env("OTEL_TRACES_EXPORTER")
    )
    logs_exporter: TelemetryExporter = Field(
        default_factory=lambda: _exporter_from_env("OTEL_LOGS_EXPORTER")
    )
    metrics_exporter: TelemetryExporter = Field(
        default_factory=lambda: _exporter_from_env("OTEL_METRICS_EXPORTER")
    )
    metric_export_interval_s: float = Field(60.0, gt=0)
    otlp_endpoint: str | None = None
    otlp_timeout_s: float = Field(10.0, gt=0)
    sample_ratio: float = Field(1.0, ge=0.0, le=1.0)
    log_level: str = Field("INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


class PipelineConfig(BaseModel):
    input_paths: list[str] = Field(default_factory=list)
    output_dir: Path = Path("output")
    recursive: bool = True
    exports: list[ExportFormat] = Field(
        default_factory=lambda: [ExportFormat.MARKDOWN, ExportFormat.JSON]
    )
    skip_existing: bool = False
    raise_on_error: bool = False
    conversion: ConversionConfig = Field(default_factory=ConversionConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineConfig:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
