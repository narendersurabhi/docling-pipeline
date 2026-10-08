"""Shared test helpers (importable because `tests` is on pytest's pythonpath)."""

from pathlib import Path

from docling.document_converter import DocumentConverter

from docling_pipeline.config import ChunkerType, ChunkingConfig, PipelineConfig


def make_config(inputs: list[Path], out: Path, **overrides) -> PipelineConfig:
    """Offline config: model-free formats and the structure-only chunker (NFR-002)."""
    return PipelineConfig(
        input_paths=[str(p) for p in inputs],
        output_dir=out,
        chunking=ChunkingConfig(chunker=ChunkerType.HIERARCHICAL),
        **overrides,
    )


class FailingConverter:
    """Wraps a real converter but raises for sources whose name contains `fail_on`."""

    def __init__(self, fail_on: str):
        self.fail_on = fail_on
        self.inner = DocumentConverter()
        self.calls: list[str] = []

    def convert(self, source, **kwargs):
        self.calls.append(str(source))
        if self.fail_on in str(source):
            raise RuntimeError("simulated parser crash")
        return self.inner.convert(source, **kwargs)
