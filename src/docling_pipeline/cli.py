"""Command-line interface: `docling-pipeline run ...`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from docling_pipeline import __version__
from docling_pipeline.config import ChunkerType, ExportFormat, PipelineConfig, TelemetryExporter
from docling_pipeline.observability import setup_telemetry
from docling_pipeline.pipeline import DocumentPipeline, DocumentResult

app = typer.Typer(add_completion=False, help="Batch document pipeline built on Docling.")
console = Console()
_state = {"console_level": logging.WARNING}


@app.callback()
def main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")] = False,
) -> None:
    _state["console_level"] = logging.DEBUG if verbose else logging.WARNING


@app.command()
def version() -> None:
    """Print the package version."""
    console.print(__version__)


@app.command()
def run(
    inputs: Annotated[
        list[str] | None,
        typer.Argument(help="Files, directories, or http(s) URLs. Overrides config input_paths."),
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", "-c", exists=True, help="YAML config file.")
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output directory.")] = None,
    formats: Annotated[
        list[ExportFormat] | None,
        typer.Option("--format", "-f", help="Export format (repeatable)."),
    ] = None,
    ocr: Annotated[bool | None, typer.Option("--ocr/--no-ocr", help="Run OCR on PDFs.")] = None,
    tables: Annotated[
        bool | None, typer.Option("--tables/--no-tables", help="Run table structure model.")
    ] = None,
    device: Annotated[str | None, typer.Option(help="auto, cpu, mps, cuda, cuda:N, xpu.")] = None,
    chunk: Annotated[bool | None, typer.Option("--chunk/--no-chunk", help="Write chunks.")] = None,
    chunker: Annotated[ChunkerType | None, typer.Option(help="Chunking strategy.")] = None,
    max_tokens: Annotated[int | None, typer.Option(help="Max tokens per hybrid chunk.")] = None,
    skip_existing: Annotated[
        bool | None,
        typer.Option("--skip-existing/--no-skip-existing", help="Skip already-converted docs."),
    ] = None,
    telemetry: Annotated[
        TelemetryExporter | None,
        typer.Option(help="Exporter for both traces and logs."),
    ] = None,
    otlp_endpoint: Annotated[
        str | None, typer.Option(help="OTLP/HTTP base URL, e.g. http://localhost:4318.")
    ] = None,
) -> None:
    """Convert documents, export them, and chunk them for retrieval."""
    cfg = PipelineConfig.from_yaml(config) if config else PipelineConfig()
    if inputs:
        cfg.input_paths = inputs
    if output is not None:
        cfg.output_dir = output
    if formats:
        cfg.exports = formats
    if ocr is not None:
        cfg.conversion.do_ocr = ocr
    if tables is not None:
        cfg.conversion.do_table_structure = tables
    if device is not None:
        cfg.conversion.device = device
    if chunk is not None:
        cfg.chunking.enabled = chunk
    if chunker is not None:
        cfg.chunking.chunker = chunker
    if max_tokens is not None:
        cfg.chunking.max_tokens = max_tokens
    if skip_existing is not None:
        cfg.skip_existing = skip_existing
    if telemetry is not None:
        cfg.observability.traces_exporter = telemetry
        cfg.observability.logs_exporter = telemetry
    if otlp_endpoint is not None:
        cfg.observability.otlp_endpoint = otlp_endpoint
    cfg = PipelineConfig.model_validate(cfg.model_dump())

    if not cfg.input_paths:
        raise typer.BadParameter("No inputs given (pass paths/URLs or set input_paths in config).")

    def report(r: DocumentResult) -> None:
        style = "green" if r.ok else ("yellow" if r.status == "skipped" else "red")
        console.print(f"[{style}]{r.status:>15}[/] {r.name} ({r.seconds:.1f}s)")

    tel = setup_telemetry(
        cfg.observability,
        console_level=_state["console_level"],
        console_handler=RichHandler(console=console, show_path=False),
    )
    try:
        summary = DocumentPipeline(cfg).run(on_result=report)
    finally:
        tel.shutdown()

    table = Table(title=f"Results -> {summary.output_dir}")
    for col in ("document", "status", "pages", "chunks", "seconds"):
        table.add_column(col)
    for r in summary.results:
        table.add_row(r.name, r.status, str(r.num_pages), str(r.num_chunks), f"{r.seconds:.1f}")
    console.print(table)
    console.print(f"trace_id: {summary.trace_id}")

    if any(r.status == "failure" for r in summary.results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
