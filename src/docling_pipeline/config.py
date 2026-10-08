"""Pipeline configuration, loadable from YAML and overridable from the CLI."""

from __future__ import annotations

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

    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineConfig:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)
