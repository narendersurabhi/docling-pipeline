"""Orchestrates discover -> convert -> export -> chunk -> manifest, with tracing (spec 002)."""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from docling.datamodel.base_models import ConversionStatus
from docling.document_converter import DocumentConverter
from opentelemetry.trace import Span, Status, StatusCode

from docling_pipeline.chunking import build_chunker, write_chunks
from docling_pipeline.config import PipelineConfig
from docling_pipeline.converter import build_converter
from docling_pipeline.exporters import export_document
from docling_pipeline.observability import current_ids, tracer
from docling_pipeline.sources import Source, discover

log = logging.getLogger(__name__)

META_FILE = "meta.json"
CHUNKS_FILE = "chunks.jsonl"
MANIFEST_FILE = "manifest.json"
_OK = {ConversionStatus.SUCCESS.value, ConversionStatus.PARTIAL_SUCCESS.value}
SKIPPED = ConversionStatus.SKIPPED.value
FAILURE = ConversionStatus.FAILURE.value


@dataclass
class DocumentResult:
    source: str
    name: str
    status: str
    output_dir: str
    files: dict[str, str] = field(default_factory=dict)
    num_pages: int = 0
    num_chunks: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    trace_id: str = ""
    span_id: str = ""

    @property
    def ok(self) -> bool:
        return self.status in _OK


@dataclass
class RunSummary:
    started_at: str
    finished_at: str
    output_dir: str
    results: list[DocumentResult]
    trace_id: str = ""

    @property
    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_dir": self.output_dir,
            "counts": self.counts,
            "documents": [asdict(r) for r in self.results],
        }


class DocumentPipeline:
    def __init__(self, config: PipelineConfig, converter: DocumentConverter | None = None):
        self.config = config
        self._converter = converter
        self._chunker = None

    @property
    def converter(self) -> DocumentConverter:
        if self._converter is None:
            self._converter = build_converter(self.config.conversion)
        return self._converter

    @property
    def chunker(self):
        if self._chunker is None:
            self._chunker = build_chunker(self.config.chunking)
        return self._chunker

    def _already_done(self, out_dir: Path) -> DocumentResult | None:
        meta = out_dir / META_FILE
        if not (self.config.skip_existing and meta.exists()):
            return None
        data = json.loads(meta.read_text(encoding="utf-8"))
        return DocumentResult(**data) if data.get("status") in _OK else None

    def process(self, source: Source) -> DocumentResult:
        with tracer.start_as_current_span(
            "document.process",
            attributes={
                "doc.name": source.name,
                "doc.source": source.location,
                "doc.is_url": source.is_url,
            },
        ) as span:
            result, exc = self._process(source, span)
            span.set_attributes(
                {
                    "doc.status": result.status,
                    "doc.pages": result.num_pages,
                    "doc.chunks": result.num_chunks,
                }
            )
            extra = {"doc.name": result.name, "doc.status": result.status}
            if result.status == SKIPPED:
                log.info("document skipped: %s", result.name, extra=extra)
            elif result.ok:
                log.info(
                    "document processed: %s (%d pages, %d chunks, %.2fs)",
                    result.name,
                    result.num_pages,
                    result.num_chunks,
                    result.seconds,
                    extra=extra,
                )
            else:
                span.set_status(Status(StatusCode.ERROR, "; ".join(result.errors)[:500]))
                log.error(
                    "document failed: %s: %s", result.name, result.errors, exc_info=exc, extra=extra
                )
            return result

    def _process(self, source: Source, span: Span) -> tuple[DocumentResult, Exception | None]:
        out_dir = Path(self.config.output_dir) / source.name
        if (done := self._already_done(out_dir)) is not None:
            done.status = SKIPPED
            span.add_event("skipped", {"reason": "existing successful meta.json"})
            return done, None

        trace_id, span_id = current_ids()
        result = DocumentResult(
            source=source.location,
            name=source.name,
            status=FAILURE,
            output_dir=str(out_dir),
            trace_id=trace_id,
            span_id=span_id,
        )
        conv = self.config.conversion
        error: Exception | None = None
        start = time.perf_counter()
        try:
            with tracer.start_as_current_span("document.convert") as convert_span:
                res = self.converter.convert(
                    source.location,
                    raises_on_error=False,
                    max_num_pages=conv.max_num_pages or sys.maxsize,
                    max_file_size=int(conv.max_file_size_mb * 1024 * 1024)
                    if conv.max_file_size_mb
                    else sys.maxsize,
                )
                result.status = res.status.value
                result.errors = [e.error_message for e in res.errors]
                convert_span.set_attribute("docling.status", result.status)
                for err in result.errors:
                    convert_span.add_event("conversion.error", {"message": err})
                if result.ok:
                    result.num_pages = res.document.num_pages()
                    convert_span.set_attribute("doc.pages", result.num_pages)
                else:
                    convert_span.set_status(Status(StatusCode.ERROR, result.status))

            if result.ok:
                doc = res.document
                with tracer.start_as_current_span(
                    "document.export",
                    attributes={"export.formats": [f.value for f in self.config.exports]},
                ):
                    result.files = export_document(doc, out_dir, self.config.exports)
                if self.config.chunking.enabled:
                    with tracer.start_as_current_span(
                        "document.chunk",
                        attributes={"chunker.type": self.config.chunking.chunker.value},
                    ) as chunk_span:
                        path = out_dir / CHUNKS_FILE
                        result.num_chunks = write_chunks(doc, self.chunker, source.location, path)
                        result.files["chunks"] = str(path)
                        chunk_span.set_attribute("chunks.count", result.num_chunks)
        except Exception as exc:  # one bad document must not stop the batch (FR-006)
            if self.config.raise_on_error:
                raise
            span.record_exception(exc)
            error = exc
            result.status = FAILURE
            result.errors.append(f"{type(exc).__name__}: {exc}")
        result.seconds = round(time.perf_counter() - start, 3)

        if result.status == FAILURE and self.config.raise_on_error:
            raise RuntimeError(f"Conversion failed for {source.location}: {result.errors}")

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / META_FILE).write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
        return result, error

    def run(self, on_result: Callable[[DocumentResult], None] | None = None) -> RunSummary:
        cfg = self.config
        with tracer.start_as_current_span(
            "pipeline.run",
            attributes={
                "pipeline.inputs": list(cfg.input_paths),
                "pipeline.output_dir": str(cfg.output_dir),
                "pipeline.exports": [f.value for f in cfg.exports],
                "pipeline.chunker": cfg.chunking.chunker.value if cfg.chunking.enabled else "none",
            },
        ) as span:
            trace_id, _ = current_ids()
            started = datetime.now(UTC).isoformat()

            with tracer.start_as_current_span("pipeline.discover") as discover_span:
                sources = discover(cfg.input_paths, recursive=cfg.recursive)
                discover_span.set_attribute("discover.sources", len(sources))
            log.info("pipeline run started: %d document(s)", len(sources))

            results = []
            for source in sources:
                result = self.process(source)
                results.append(result)
                if on_result:
                    on_result(result)

            summary = RunSummary(
                started_at=started,
                finished_at=datetime.now(UTC).isoformat(),
                output_dir=str(cfg.output_dir),
                results=results,
                trace_id=trace_id,
            )
            counts = summary.counts
            span.set_attributes(
                {
                    "pipeline.documents.total": len(results),
                    "pipeline.documents.succeeded": sum(r.ok for r in results),
                    "pipeline.documents.failed": counts.get(FAILURE, 0),
                    "pipeline.documents.skipped": counts.get(SKIPPED, 0),
                }
            )
            out = Path(cfg.output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / MANIFEST_FILE).write_text(
                json.dumps(summary.to_dict(), indent=2), encoding="utf-8"
            )
            log.info("pipeline run finished: %s", counts)
            return summary
